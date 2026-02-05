import streamlit as st
import pandas as pd
from datetime import datetime
import json
import hashlib
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from fpdf import FPDF
from supabase import create_client, Client

# --- CONFIGURAÇÕES DE EMAIL (Mantenha seus dados aqui) ---
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
EMAIL_REMETENTE = "seu_email@gmail.com"
EMAIL_SENHA = "sua_senha_de_app"
EMAIL_DESTINATARIO_LIDER = "email_lider@empresa.com"

# --- CONFIGURAÇÕES DO SUPABASE ---
SUPABASE_URL = "https://zjllenyumadtegnvuuwj.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InpqbGxlbnl1bWFkdGVnbnZ1dXdqIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzAyMzc4ODEsImV4cCI6MjA4NTgxMzg4MX0.ZTEhjAkb8W9wXayHbE3n7ixCD4t8Gh2wSC7cYRLwtjA"

# Conexão com Supabase (Cache para não reconectar toda hora)
@st.cache_resource
def init_supabase():
    return create_client(SUPABASE_URL, SUPABASE_KEY)

supabase = init_supabase()

# --- 1. CONFIGURAÇÃO E CSS ---
st.set_page_config(
    page_title="Gestão de Frota - STS 14",
    page_icon="🚜",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
    <style>
    div[data-testid="stMetric"] {
        background-color: #262730;
        border: 1px solid #464b5f;
        padding: 15px;
        border-radius: 10px;
        color: white;
    }
    .stButton>button {
        width: 100%;
        border-radius: 8px;
        height: 3em;
    }
    </style>
""", unsafe_allow_html=True)

# --- 2. FUNÇÕES AUXILIARES ---

def hash_senha(senha):
    return hashlib.sha256(senha.encode()).hexdigest()

def verificar_login(username, senha):
    try:
        # Busca usuário no Supabase
        response = supabase.table('usuarios').select("*").eq('username', username).execute()
        
        # Verifica se há dados
        if response.data and len(response.data) > 0:
            user_data = response.data[0]
            senha_hash_digitada = hash_senha(senha)
            
            # Compara hash da senha
            if user_data.get('senha_hash') == senha_hash_digitada:
                # Retorna True e status admin (converte para bool se vier como int)
                is_admin = bool(user_data.get('is_admin', 0))
                return True, is_admin
        
        return False, False
        
    except Exception as e:
        st.error(f"Erro de conexão com o banco: {e}")
        return False, False

# --- 3. ENVIO DE E-MAIL ---
def enviar_alerta_bloqueio(dados, itens_nok):
    assunto = f"ALERTA: Empilhadeira {dados['frota']} BLOQUEADA"
    corpo_email = f"""
    <h2>Máquina Bloqueada - Operação Interrompida</h2>
    <p><b>Data:</b> {datetime.now().strftime("%d/%m/%Y %H:%M")}<br>
    <b>Operador:</b> {dados['operador']} ({dados['empresa']})<br>
    <b>Frota:</b> {dados['frota']}<br>
    <b>Horímetro:</b> {int(dados['horimetro_inicial'])}</p>
    <h3>Itens Reprovados:</h3><ul>
    """
    for item in itens_nok:
        corpo_email += f"<li>❌ {item}</li>"
    corpo_email += "</ul>"

    try:
        msg = MIMEMultipart()
        msg['From'] = EMAIL_REMETENTE
        msg['To'] = EMAIL_DESTINATARIO_LIDER
        msg['Subject'] = assunto
        msg.attach(MIMEText(corpo_email, 'html'))
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(EMAIL_REMETENTE, EMAIL_SENHA)
        server.send_message(msg)
        server.quit()
        return True
    except Exception as e:
        print(f"Erro email: {e}")
        return False

# --- 4. GERAÇÃO DE PDF ---
class PDF(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 15)
        self.cell(0, 10, 'Relatório de Inspeção - STS 14', 0, 1, 'C')
        self.ln(5)

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, f'Página {self.page_no()}', 0, 0, 'C')

def gerar_pdf_bytes(df):
    pdf = PDF(orientation='L')
    pdf.add_page()
    pdf.set_font("Arial", size=10)
    
    cols = ['Data', 'Frota', 'Operador', 'Status Check', 'H. Inicial', 'H. Final']
    larguras = [45, 25, 60, 35, 25, 25]
    
    pdf.set_fill_color(200, 220, 255)
    for i, col in enumerate(cols):
        pdf.cell(larguras[i], 10, col, 1, 0, 'C', 1)
    pdf.ln()
    
    for index, row in df.iterrows():
        try:
            data_fmt = pd.to_datetime(row['Data']).strftime("%d/%m/%Y %H:%M")
        except: 
            data_fmt = str(row['Data'])
            
        pdf.cell(larguras[0], 10, data_fmt, 1)
        pdf.cell(larguras[1], 10, str(row['Frota']), 1)
        pdf.cell(larguras[2], 10, str(row['Operador'])[:25], 1)
        pdf.cell(larguras[3], 10, str(row['Status Check']), 1)
        pdf.cell(larguras[4], 10, str(int(row['H. Inicial'])), 1)
        pdf.cell(larguras[5], 10, str(int(row['H. Final'])), 1)
        pdf.ln()
        
    return pdf.output(dest='S').encode('latin-1')

# --- 5. ESTILO DA TABELA ---
def colorir_status(val):
    if val == 'BLOQUEADO':
        return 'background-color: #5a1a1a; color: #ffcccc; font-weight: bold;'
    elif val == 'LIBERADO':
        return 'background-color: #15381b; color: #ccffcc; font-weight: bold;'
    return ''

# --- 6. TELAS DO SISTEMA ---
def tela_login():
    col1, col2, col3 = st.columns([1,1,1])
    with col2:
        st.title("🔐 Acesso Restrito")
        with st.form("login_form"):
            username = st.text_input("Usuário")
            senha = st.text_input("Senha", type="password")
            if st.form_submit_button("Entrar"):
                if not username or not senha:
                    st.error("Por favor, preencha usuário e senha.")
                else:
                    sucesso, is_admin = verificar_login(username, senha)
                    if sucesso:
                        st.session_state['logado'] = True
                        st.session_state['usuario'] = username
                        st.session_state['is_admin'] = is_admin
                        st.rerun()
                    else:
                        st.error("Login incorreto. Verifique usuário e senha.")

def tela_historico_bonita():
    st.title("📊 Painel de Histórico")
    
    # Busca dados no Supabase
    try:
        response = supabase.table('inspecoes').select("*").order('id', desc=True).execute()
        df = pd.DataFrame(response.data)
    except Exception as e:
        st.error(f"Erro ao buscar dados: {e}")
        return

    if df.empty:
        st.info("Nenhuma inspeção realizada ainda.")
        return

    # Processamento de Datas
    df['data_hora_dt'] = pd.to_datetime(df['data_hora'])
    df['Ano'] = df['data_hora_dt'].dt.year
    df['Mes_Num'] = df['data_hora_dt'].dt.month
    MAPA_MESES = {
        1: 'Janeiro', 2: 'Fevereiro', 3: 'Março', 4: 'Abril', 5: 'Maio', 6: 'Junho',
        7: 'Julho', 8: 'Agosto', 9: 'Setembro', 10: 'Outubro', 11: 'Novembro', 12: 'Dezembro'
    }
    df['Mes_Nome'] = df['Mes_Num'].map(MAPA_MESES)

    lista_anos = sorted(df['Ano'].unique(), reverse=True)
    meses_presentes_num = sorted(df['Mes_Num'].unique())
    lista_meses = [MAPA_MESES[m] for m in meses_presentes_num]
    lista_frotas = sorted(df['frota'].unique())
    lista_tipos = sorted(df['tipo_maquina'].unique())

    with st.container(border=True):
        st.caption("🔍 Filtros de Pesquisa")
        c1, c2, c3, c4 = st.columns(4)
        with c1: ano_sel = st.selectbox("Ano", ["Todos"] + list(lista_anos))
        with c2: mes_sel = st.selectbox("Mês", ["Todos"] + list(lista_meses))
        with c3: frota_sel = st.selectbox("Frota", ["Todas"] + list(lista_frotas))
        with c4: tipo_sel = st.selectbox("Tipo Máquina", ["Todos"] + list(lista_tipos))

    df_filtered = df.copy()
    if ano_sel != "Todos": df_filtered = df_filtered[df_filtered['Ano'] == ano_sel]
    if mes_sel != "Todos": df_filtered = df_filtered[df_filtered['Mes_Nome'] == mes_sel]
    if frota_sel != "Todas": df_filtered = df_filtered[df_filtered['frota'] == frota_sel]
    if tipo_sel != "Todos": df_filtered = df_filtered[df_filtered['tipo_maquina'] == tipo_sel]

    # Dashboard
    total = len(df_filtered)
    bloqueadas = len(df_filtered[df_filtered['resultado_geral'] == 'BLOQUEADO'])
    abertas = len(df_filtered[df_filtered['status_turno'] == 'ABERTO'])

    m1, m2, m3 = st.columns(3)
    m1.metric("📋 Total Registros", total)
    m2.metric("🚜 Em Operação", abertas)
    m3.metric("⛔ Bloqueios", bloqueadas)
    st.markdown("---")

    # Tratamento colunas ausentes (caso existam registros antigos)
    for col in ['horimetro_final', 'empresa_operador', 'usuario_sistema', 'status_turno']:
        if col not in df_filtered.columns: df_filtered[col] = '-'

    df_show = df_filtered[['id', 'data_hora', 'frota', 'tipo_maquina', 'operador', 'empresa_operador', 'resultado_geral', 'status_turno', 'horimetro_inicial', 'horimetro_final']]
    
    df_show = df_show.rename(columns={
        'id': 'ID',
        'data_hora': 'Data',
        'frota': 'Frota',
        'tipo_maquina': 'Tipo',
        'operador': 'Operador',
        'empresa_operador': 'Empresa',
        'resultado_geral': 'Status Check',
        'status_turno': 'Status Turno',
        'horimetro_inicial': 'H. Inicial',
        'horimetro_final': 'H. Final'
    })

    st.dataframe(
        df_show.style.applymap(colorir_status, subset=['Status Check']),
        use_container_width=True,
        hide_index=True,
        column_config={
            "H. Inicial": st.column_config.NumberColumn(format="%d"), 
            "H. Final": st.column_config.NumberColumn(format="%d")
        }
    )
    
    c_dl1, c_dl2 = st.columns(2)
    with c_dl1:
        csv = df_show.to_csv(index=False).encode('utf-8')
        st.download_button("📥 Baixar Planilha (CSV)", csv, "relatorio.csv", "text/csv")
    with c_dl2:
        try:
            pdf_bytes = gerar_pdf_bytes(df_show)
            st.download_button("📄 Baixar Relatório PDF", pdf_bytes, "relatorio.pdf", "application/pdf")
        except Exception as e:
            st.error(f"Erro ao gerar PDF: {e}")

    # --- ÁREA DE EDIÇÃO (ADMIN) ---
    if st.session_state.get('is_admin'):
        st.markdown("---")
        st.subheader("⚙️ Gestão de Registros (Área Admin)")
        
        with st.expander("🛠️ Editar ou Excluir Registro"):
            id_para_editar = st.selectbox("Selecione o ID para gerenciar:", df_show['ID'])
            
            # Fetch single row from Supabase
            try:
                res_single = supabase.table('inspecoes').select("*").eq('id', int(id_para_editar)).execute()
                
                if len(res_single.data) > 0:
                    dados_atuais = res_single.data[0]
                    c_edit1, c_edit2 = st.columns(2)
                    
                    with c_edit1:
                        st.write("### Editar Dados")
                        
                        # Conversão para INT para remover aviso amarelo
                        try:
                            val_ini = int(float(dados_atuais.get('horimetro_inicial') or 0))
                            val_fin = int(float(dados_atuais.get('horimetro_final') or 0))
                        except:
                            val_ini = 0
                            val_fin = 0
                        
                        novo_h_ini = st.number_input("Corrigir H. Inicial", value=val_ini, step=1, format="%d")
                        novo_h_fin = st.number_input("Corrigir H. Final", value=val_fin, step=1, format="%d")
                        
                        idx_status = 0 if dados_atuais.get('status_turno') == "ABERTO" else 1
                        novo_status_turno = st.selectbox("Status Turno", ["ABERTO", "FECHADO"], index=idx_status)
                        
                        if st.button("💾 Salvar Alterações"):
                            supabase.table('inspecoes').update({
                                'horimetro_inicial': novo_h_ini,
                                'horimetro_final': novo_h_fin,
                                'status_turno': novo_status_turno
                            }).eq('id', int(id_para_editar)).execute()
                            st.success("Registro atualizado!")
                            st.rerun()

                    with c_edit2:
                        st.write("### Zona de Perigo")
                        st.warning("A exclusão é permanente.")
                        if st.button("🗑️ EXCLUIR REGISTRO", type="primary"):
                            supabase.table('inspecoes').delete().eq('id', int(id_para_editar)).execute()
                            st.error("Registro excluído!")
                            st.rerun()
            except Exception as e:
                st.error(f"Erro ao carregar registro: {e}")

def tela_checklist():
    st.header("📝 Controle Operacional")
    
    tipo_acao = st.radio("Selecione a Ação:", ["🟢 Iniciar Turno (Check-list)", "🔴 Encerrar Turno (Inserir Horímetro Final)"], horizontal=True)
    st.markdown("---")
    
    if "Iniciar" in tipo_acao:
        # Busca Frota e Operadores
        try:
            res_frota = supabase.table('frota').select("*").execute()
            df_frota = pd.DataFrame(res_frota.data)
            
            res_ops = supabase.table('operadores').select("*").order('nome').execute()
            df_operadores = pd.DataFrame(res_ops.data)
        except Exception as e:
            st.error(f"Erro ao carregar dados auxiliares do Supabase: {e}")
            return
        
        if df_frota.empty or df_operadores.empty:
            st.warning("Cadastre Frota e Operadores primeiro (Menu Admin).")
            return

        with st.container(border=True):
            st.subheader("1. Início de Operação")
            c_op1, c_op2 = st.columns(2)
            with c_op1:
                nome_operador = st.selectbox("Operador", df_operadores['nome'])
            with c_op2:
                # Recupera empresa do operador
                empresa_operador = df_operadores[df_operadores['nome'] == nome_operador]['empresa'].values[0]
                st.text_input("Empresa", value=empresa_operador, disabled=True)

            c1, c2 = st.columns(2)
            with c1:
                frota_selecionada = st.selectbox("Máquina", df_frota['numero_maquina'])
                tipo_maquina = df_frota[df_frota['numero_maquina'] == frota_selecionada]['tipo_maquina'].values[0]
                st.caption(f"Tipo: {tipo_maquina}")
            with c2:
                turno = st.selectbox("Turno", ["07 X 13", "13 X 19", "19 X 01", "01 X 07"])
            
            h_inicial = st.number_input("Horímetro INICIAL", min_value=0, step=1, format="%d")

        # Itens do Checklist
        ITENS_COMUNS_IMPEDITIVOS = ["Buzina", "Travas de Garfo", "Cinto de Segurança", "Direção", "Freio"]
        if "Elétrica" in tipo_maquina:
            lista_impeditivos = ITENS_COMUNS_IMPEDITIVOS + ["Botão de Emergência"]
            lista_manutencao = ["Espelho Retrovisor", "Extintor", "Giroflex", "Sirene de Ré", "Carga Bateria", "Mangueiras", "Rodas/Pneus"]
        else:
            lista_impeditivos = ITENS_COMUNS_IMPEDITIVOS + ["Suporte Cilindro GLP"]
            lista_manutencao = ["Espelho Retrovisor", "Extintor", "Giroflex", "Sirene de Ré", "Nível Óleo Motor", "Mangueiras", "Rodas/Pneus"]

        respostas = {}
        itens_nok_criticos = []
        
        st.subheader("2. Inspeção")
        with st.expander("🚨 ITENS IMPEDITIVOS", expanded=True):
            cols = st.columns(3)
            for i, item in enumerate(lista_impeditivos):
                with cols[i % 3]:
                    val = st.radio(f"**{item}**", ("OK", "NOK"), key=f"imp_{item}", horizontal=True)
                    respostas[item] = val
                    if val == "NOK": itens_nok_criticos.append(item)

        with st.expander("🛠️ ITENS MANUTENÇÃO"):
            cols = st.columns(3)
            for i, item in enumerate(lista_manutencao):
                with cols[i % 3]:
                    val = st.radio(item, ("OK", "NOK"), key=f"man_{item}", horizontal=True)
                    respostas[item] = val

        if st.button("✅ Salvar Início de Turno", type="primary"):
            resultado_final = "BLOQUEADO" if itens_nok_criticos else "LIBERADO"
            
            data_insert = {
                "data_hora": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "tipo_maquina": tipo_maquina,
                "frota": frota_selecionada,
                "turno": turno,
                "operador": nome_operador,
                "empresa_operador": empresa_operador,
                "usuario_sistema": st.session_state['usuario'],
                "horimetro_inicial": h_inicial,
                "horimetro_final": 0,
                "resultado_geral": resultado_final,
                "detalhes_json": json.dumps(respostas),
                "status_turno": 'ABERTO'
            }
            
            try:
                supabase.table('inspecoes').insert(data_insert).execute()
                
                if resultado_final == "BLOQUEADO":
                    st.error("⛔ MÁQUINA BLOQUEADA!")
                    enviar_alerta_bloqueio({"frota": frota_selecionada, "operador": nome_operador, "empresa": empresa_operador, "horimetro_inicial": h_inicial}, itens_nok_criticos)
                else:
                    st.success("✅ Turno Iniciado com Sucesso!")
            except Exception as e:
                st.error(f"Erro ao salvar: {e}")

    else:
        # --- MODO ENCERRAR TURNO ---
        try:
            response = supabase.table('inspecoes').select("*").eq('status_turno', 'ABERTO').execute()
            df_abertos = pd.DataFrame(response.data)
        except:
            df_abertos = pd.DataFrame()

        if df_abertos.empty:
            st.info("Não há turnos abertos para encerrar.")
        else:
            st.subheader("Selecione o Turno para Encerrar")
            opcoes = df_abertos.apply(lambda x: f"ID: {x['id']} | {x['frota']} | {x['operador']} | Início: {int(x.get('horimetro_inicial',0))}", axis=1)
            escolha = st.selectbox("Selecione o Registro em Aberto:", options=df_abertos['id'], format_func=lambda x: opcoes[df_abertos['id'] == x].values[0])
            
            st.markdown("---")
            with st.form("form_fechar"):
                h_final_input = st.number_input("Horímetro FINAL", min_value=0, step=1, format="%d")
                obs_final = st.text_area("Observações Finais")
                
                if st.form_submit_button("💾 Finalizar Turno"):
                    supabase.table('inspecoes').update({
                        'horimetro_final': h_final_input,
                        'status_turno': 'FECHADO'
                    }).eq('id', int(escolha)).execute()
                    
                    st.success("✅ Turno Encerrado e Horímetro Atualizado!")
                    st.rerun()

# --- TELAS ADMIN ---
def tela_admin_frota():
    st.header("🚜 Gerenciar Frota")
    c1, c2, c3 = st.columns([2, 2, 1])
    with c1: num = st.text_input("Nº Frota (Ex: EMP-01)")
    with c2: tipo = st.selectbox("Tipo", ["Empilhadeira Elétrica", "Empilhadeira a Gás"])
    with c3: 
        st.write("") 
        st.write("")
        if st.button("➕ Add"):
            if num:
                num_upper = num.upper()
                try:
                    supabase.table('frota').insert({"numero_maquina": num_upper, "tipo_maquina": tipo}).execute()
                    st.success(f"Máquina {num_upper} adicionada!")
                except Exception as e: st.error(f"Erro: {e}")
    
    res = supabase.table('frota').select("*").execute()
    df_frota = pd.DataFrame(res.data)
    if not df_frota.empty:
        df_frota = df_frota.rename(columns={'numero_maquina': 'Nº Máquina', 'tipo_maquina': 'Tipo'})
        st.dataframe(df_frota, use_container_width=True, hide_index=True)

def tela_admin_operadores():
    st.header("👷 Gerenciar Operadores")
    with st.expander("Cadastrar Novo Operador", expanded=True):
        c1, c2 = st.columns(2)
        with c1: novo_nome = st.text_input("Nome Completo")
        with c2: nova_empresa = st.selectbox("Empresa", ["OGMO", "DEEP", "TERCEIRO", "OUTRO"])
            
        if st.button("Salvar Operador"):
            if novo_nome:
                try:
                    # FORÇA MAIÚSCULO
                    supabase.table('operadores').insert({"nome": novo_nome.upper(), "empresa": nova_empresa}).execute()
                    st.success("Cadastrado!")
                    st.rerun()
                except Exception as e: st.error(f"Erro: {e}")

    res = supabase.table('operadores').select("*").order('nome').execute()
    df_ops = pd.DataFrame(res.data)
    if not df_ops.empty:
        df_ops = df_ops.rename(columns={'nome': 'Nome', 'empresa': 'Empresa'})
        st.dataframe(df_ops, use_container_width=True, hide_index=True)

def tela_admin_usuarios():
    st.header("👥 Usuários (Login)")
    
    with st.expander("➕ Criar Novo Usuário", expanded=True):
        c1, c2, c3, c4 = st.columns([2, 2, 1, 1])
        with c1: user = st.text_input("Usuário")
        with c2: pwd = st.text_input("Senha", type="password")
        with c3: 
            st.write("")
            admin = st.checkbox("Admin?")
        with c4:
            st.write("")
            if st.button("Criar"):
                if user and pwd:
                    try:
                        supabase.table('usuarios').insert({
                            "username": user, 
                            "senha_hash": hash_senha(pwd), 
                            "is_admin": 1 if admin else 0
                        }).execute()
                        st.success("Usuário criado com sucesso!")
                        st.rerun()
                    except Exception as e: 
                        st.error(f"Erro: {e}")
                else:
                    st.warning("Preencha usuário e senha.")
    
    st.subheader("Usuários Cadastrados")
    try:
        res = supabase.table('usuarios').select("username, is_admin").execute()
        df_users = pd.DataFrame(res.data)
        if not df_users.empty:
            df_users['is_admin'] = df_users['is_admin'].apply(lambda x: '✅ Admin' if x else '👤 Usuário')
            df_users = df_users.rename(columns={'username': 'Usuário', 'is_admin': 'Tipo'})
            st.dataframe(df_users, use_container_width=True, hide_index=True)
        else:
            st.info("Nenhum usuário cadastrado ainda.")
    except Exception as e:
        st.error(f"Erro ao carregar usuários: {e}")

# --- MAIN ---
def main():
    if 'logado' not in st.session_state: 
        st.session_state['logado'] = False
    
    if not st.session_state['logado']:
        tela_login()
    else:
        with st.sidebar:
            st.subheader(f"👤 {st.session_state['usuario']}")
            if st.session_state.get('is_admin'):
                st.caption("🔑 Administrador")
            st.write("---")
            
            opt = st.radio("Navegação", [
                "📝 Check-list", 
                "📊 Histórico", 
                "🚜 Frota (Admin)", 
                "👷 Operadores (Admin)", 
                "👥 Usuários (Admin)"
            ])
            st.write("---")
            if st.button("🚪 Sair"):
                st.session_state['logado'] = False
                st.rerun()

        if opt == "📝 Check-list": 
            tela_checklist()
        elif opt == "📊 Histórico": 
            tela_historico_bonita()
        elif opt == "🚜 Frota (Admin)": 
            if st.session_state.get('is_admin'): 
                tela_admin_frota()
            else: 
                st.error("⛔ Acesso Restrito - Apenas Administradores")
        elif opt == "👷 Operadores (Admin)": 
            if st.session_state.get('is_admin'): 
                tela_admin_operadores()
            else: 
                st.error("⛔ Acesso Restrito - Apenas Administradores")
        elif opt == "👥 Usuários (Admin)":
            if st.session_state.get('is_admin'): 
                tela_admin_usuarios()
            else: 
                st.error("⛔ Acesso Restrito - Apenas Administradores")

if __name__ == "__main__":
    main()
