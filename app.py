import streamlit as st
import pandas as pd
import io

# 1. Configuración de la página
st.set_page_config(page_title="Logística Crucianelli", page_icon="🚜", layout="wide")

# 2. BARRA LATERAL (Sidebar)
try:
    st.sidebar.image("logo.png", use_container_width=True)
except Exception:
    pass

st.sidebar.header("📂 Carga de Archivos SAP")
archivo_mb52 = st.sidebar.file_uploader("1. Subir MB52 (Stock MM)", type=['csv', 'xlsx'])
archivo_lx02 = st.sidebar.file_uploader("2. Subir LX02 (Stock WM)", type=['csv', 'xlsx'])
archivo_nt = st.sidebar.file_uploader("3. Subir NT (LB10 Abiertas)", type=['csv', 'xlsx'])
archivo_ot = st.sidebar.file_uploader("4. Subir OT (LT23 Abiertas)", type=['csv', 'xlsx'])

boton_procesar = st.sidebar.button("Procesar Datos y Analizar", type="primary", use_container_width=True)

# 3. PANTALLA PRINCIPAL
st.title("📦 Analizador de Traslados WM/MM - Crucianelli")
st.markdown("---") 

if boton_procesar:
    if archivo_mb52 and archivo_lx02 and archivo_nt and archivo_ot:
        try:
            # --- LECTURA DE ARCHIVOS ---
            df_mb52 = pd.read_csv(archivo_mb52) if archivo_mb52.name.endswith('.csv') else pd.read_excel(archivo_mb52)
            df_lx02 = pd.read_csv(archivo_lx02) if archivo_lx02.name.endswith('.csv') else pd.read_excel(archivo_lx02)
            df_nt = pd.read_csv(archivo_nt) if archivo_nt.name.endswith('.csv') else pd.read_excel(archivo_nt)
            df_ot = pd.read_csv(archivo_ot) if archivo_ot.name.endswith('.csv') else pd.read_excel(archivo_ot)
            
            # --- PROCESAMIENTO MB52 ---
            df_mb52['Trans./Trasl.'] = pd.to_numeric(df_mb52['Trans./Trasl.'], errors='coerce').fillna(0)
            df_mb52_filtrado = df_mb52[df_mb52['Trans./Trasl.'] > 0].copy()
            
            # Agrupamos por material para las matemáticas
            df_mm = df_mb52_filtrado[['Material', 'Trans./Trasl.']].groupby('Material').sum().reset_index()
            
            # Recuperamos el Almacén (destino) para usarlo en la MIGO
            df_almacenes = df_mb52_filtrado.groupby('Material')['Almacén'].first().reset_index()
            df_mm = pd.merge(df_mm, df_almacenes, on='Material', how='left')

            # --- PROCESAMIENTO WM (LX02, NT, OT) ---
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

            # --- CRUCE FINAL ---
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
            columnas_finales = ['Material', 'Almacén', 'Trans./Trasl.', 'Cant_Pendiente_NT', 'Cant_Pendiente_OT', 'Falta_Hacer_315', 'Estado Final']
            resultado_vista = resultado[columnas_finales].rename(columns={'Trans./Trasl.': 'Stock_MM_Traslado'})

            # --- ARMADO DE LA HOJA PARA MIGO ---
            # Filtramos solo los que necesitan 315
            df_migo = resultado_vista[resultado_vista['Falta_Hacer_315'] > 0].copy()
            # Ordenamos las columnas para SAP
            df_migo = df_migo[['Material', 'Falta_Hacer_315', 'Almacén']]
            df_migo.rename(columns={'Falta_Hacer_315': 'Cantidad'}, inplace=True)
            df_migo.insert(2, 'Centro', 'A110') # Agregamos la columna Centro asumiendo A110

            # --- MÉTRICAS VISUALES ---
            st.subheader("📊 Resumen del Día")
            mat_ok = len(resultado_vista[resultado_vista['Estado Final'].str.contains('OK')])
            mat_error = len(df_migo)
            unidades_perdidas = df_migo['Cantidad'].sum()

            col1, col2, col3 = st.columns(3)
            col1.metric(label="✅ Materiales OK", value=mat_ok)
            col2.metric(label="🚨 Materiales sin 315", value=mat_error)
            col3.metric(label="📦 Total Unidades a Almacenar", value=f"{unidades_perdidas:,.0f}")
            st.markdown("---")

            # --- TABLAS EN PANTALLA ---
            st.success("¡Cruce exitoso! Abajo tenés el reporte general.")
            st.dataframe(resultado_vista, use_container_width=True)

            st.warning(f"🔧 Se detectaron {mat_error} materiales que requieren ajuste en MIGO (Mov. 315). Al descargar el Excel, encontrarás una pestaña lista para copiar y pegar en SAP.")

            # --- CREACIÓN DEL EXCEL CON 2 HOJAS ---
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                resultado_vista.to_excel(writer, sheet_name='Reporte_General', index=False)
                df_migo.to_excel(writer, sheet_name='Carga_MIGO_315', index=False)
            
            excel_data = output.getvalue()

            st.download_button(
                label="📥 Descargar Excel (Reporte + Formato MIGO)",
                data=excel_data,
                file_name='Analisis_Traslados_MIGO.xlsx',
                mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                type="primary"
            )
            
        except Exception as e:
            st.error(f"❌ Ocurrió un error procesando los archivos. Detalle: {e}")
    else:
        st.warning("⚠️ Faltan archivos. Asegurate de cargar los 4 archivos en el menú izquierdo.")
else:
    st.info("👈 Cargá tus reportes de SAP en el menú de la izquierda y presioná 'Procesar Datos'.")
