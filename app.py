import streamlit as st
import pandas as pd

# 1. Configuración de la página (DEBE IR PRIMERO)
# layout="wide" hace que ocupe toda la pantalla
st.set_page_config(page_title="Logística Crucianelli", page_icon="🚜", layout="wide")

# 2. BARRA LATERAL (Sidebar)
# Intentamos cargar el logo (asegurate de que el nombre del archivo coincida)
try:
    st.sidebar.image("logo.png", use_container_width=True)
except Exception:
    st.sidebar.write("*(Subí el archivo logo.png a GitHub para verlo acá)*")

st.sidebar.header("📂 Carga de Archivos SAP")
archivo_mb52 = st.sidebar.file_uploader("1. Subir MB52 (Stock MM)", type=['csv', 'xlsx'])
archivo_lx02 = st.sidebar.file_uploader("2. Subir LX02 (Stock WM)", type=['csv', 'xlsx'])
archivo_nt = st.sidebar.file_uploader("3. Subir NT (LB10 Abiertas)", type=['csv', 'xlsx'])
archivo_ot = st.sidebar.file_uploader("4. Subir OT (LT23 Abiertas)", type=['csv', 'xlsx'])

# Botón de proceso en la barra lateral
boton_procesar = st.sidebar.button("Procesar Datos y Analizar", type="primary", use_container_width=True)

# 3. PANTALLA PRINCIPAL
st.title("📦 Analizador de Traslados WM/MM - Crucianelli")
st.markdown("---") # Línea separadora

if boton_procesar:
    if archivo_mb52 and archivo_lx02 and archivo_nt and archivo_ot:
        try:
            # --- LECTURA DE ARCHIVOS ---
            df_mb52 = pd.read_csv(archivo_mb52) if archivo_mb52.name.endswith('.csv') else pd.read_excel(archivo_mb52)
            df_lx02 = pd.read_csv(archivo_lx02) if archivo_lx02.name.endswith('.csv') else pd.read_excel(archivo_lx02)
            df_nt = pd.read_csv(archivo_nt) if archivo_nt.name.endswith('.csv') else pd.read_excel(archivo_nt)
            df_ot = pd.read_csv(archivo_ot) if archivo_ot.name.endswith('.csv') else pd.read_excel(archivo_ot)
            
            # --- PROCESAMIENTO (Tu lógica perfecta) ---
            df_mb52['Trans./Trasl.'] = pd.to_numeric(df_mb52['Trans./Trasl.'], errors='coerce').fillna(0)
            df_mm = df_mb52[df_mb52['Trans./Trasl.'] > 0][['Material', 'Trans./Trasl.']].groupby('Material').sum().reset_index()

            nts_abiertas = set(pd.to_numeric(df_nt['Nº NT'], errors='coerce').dropna())
            ots_abiertas = set(pd.to_numeric(df_ot['Número de orden de transporte'], errors='coerce').dropna())

            df_lx02['Tipo almacén'] = df_lx02['Tipo almacén'].astype(str)
            df_lx02['Stock disponible'] = pd.to_numeric(df_lx02['Stock disponible'], errors='coerce').fillna(0)
            df_lx02['Nº NT'] = pd.to_numeric(df_lx02['Nº NT'], errors='coerce').fillna(0)
            df_lx02['Ref_OT_Doc'] = pd.to_numeric(df_lx02['Número de orden de transporte'], errors='coerce').fillna(0)

            df_wm = df_lx02[(df_lx02['Tipo almacén'] == '921') & (df_lx02['Stock disponible'] != 0)].copy()

            def clasificar_linea_wm(row):
                if row['Nº NT'] in nts_abiertas:
                    return 'Cant_Pendiente_NT'
                elif row['Ref_OT_Doc'] in ots_abiertas:
                    return 'Cant_Pendiente_OT'
                else:
                    return 'Cant_Fantasma_WM'

            df_wm['Estado_WM'] = df_wm.apply(clasificar_linea_wm, axis=1)
            df_wm['Stock disponible'] = df_wm['Stock disponible'].abs()
            df_wm_agrupado = df_wm.pivot_table(index='Material', columns='Estado_WM', values='Stock disponible', aggfunc='sum').fillna(0).reset_index()

            for col in ['Cant_Pendiente_NT', 'Cant_Pendiente_OT', 'Cant_Fantasma_WM']:
                if col not in df_wm_agrupado.columns:
                    df_wm_agrupado[col] = 0

            resultado = pd.merge(df_mm, df_wm_agrupado, on='Material', how='left').fillna(0)
            resultado['WM_Justificado'] = resultado['Cant_Pendiente_NT'] + resultado['Cant_Pendiente_OT']
            resultado['Falta_Hacer_315'] = resultado['Trans./Trasl.'] - resultado['WM_Justificado']

            def estado_final(row):
                if row['Falta_Hacer_315'] > 0:
                    return "🚨 ERROR - Falta 315"
                elif row['Falta_Hacer_315'] < 0:
                    return "⚠️ ERROR - Diferencia WM/MM"
                else:
                    return "✅ OK - Pendiente Picking"

            resultado['Estado Final'] = resultado.apply(estado_final, axis=1)
            columnas_finales = ['Material', 'Trans./Trasl.', 'Cant_Pendiente_NT', 'Cant_Pendiente_OT', 'Falta_Hacer_315', 'Estado Final']
            resultado_vista = resultado[columnas_finales].rename(columns={'Trans./Trasl.': 'Stock_MM_Traslado'})

            # --- 4. MÉTRICAS VISUALES (Tablero de Control) ---
            st.subheader("📊 Resumen del Día")
            
            # Cálculos rápidos
            mat_ok = len(resultado_vista[resultado_vista['Estado Final'].str.contains('OK')])
            mat_error = len(resultado_vista[resultado_vista['Estado Final'].str.contains('ERROR - Falta 315')])
            unidades_perdidas = resultado_vista[resultado_vista['Falta_Hacer_315'] > 0]['Falta_Hacer_315'].sum()

            # Mostramos las métricas en 3 columnas
            col1, col2, col3 = st.columns(3)
            col1.metric(label="✅ Materiales OK", value=mat_ok)
            col2.metric(label="🚨 Materiales sin 315", value=mat_error)
            col3.metric(label="📦 Total Unidades a Almacenar", value=f"{unidades_perdidas:,.0f}")
            
            st.markdown("---")

            # --- 5. TABLA Y DESCARGA ---
            st.success("Cruce realizado exitosamente. Revisá el detalle a continuación:")
            st.dataframe(resultado_vista, use_container_width=True)
            
            csv = resultado_vista.to_csv(index=False, encoding='utf-8-sig').encode('utf-8-sig')
            st.download_button(
                label="📥 Descargar Reporte Completo",
                data=csv,
                file_name='Analisis_Traslados_Crucianelli.csv',
                mime='text/csv',
                type="primary"
            )
            
        except Exception as e:
            st.error(f"❌ Ocurrió un error procesando los archivos. Detalle: {e}")
    else:
        st.warning("⚠️ Faltan archivos. Asegurate de cargar los 4 archivos en el menú izquierdo.")
else:
    st.info("👈 Cargá tus reportes de SAP en el menú de la izquierda y presioná 'Procesar Datos'.")
