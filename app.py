import streamlit as st
import pandas as pd

st.title("📦 Analizador de Traslados WM/MM - Crucianelli")
st.write("Versión Mejorada: Cruce directo por NT/OT desde LX02")

# Creador de botones para subir archivos (¡Volvemos a 4 archivos!)
col1, col2 = st.columns(2)
with col1:
    archivo_mb52 = st.file_uploader("1. Subir MB52 (Stock MM)", type=['csv', 'xlsx'])
    archivo_lx02 = st.file_uploader("2. Subir LX02 (Stock WM)", type=['csv', 'xlsx'])
with col2:
    archivo_nt = st.file_uploader("3. Subir NT (LB10 Abiertas)", type=['csv', 'xlsx'])
    archivo_ot = st.file_uploader("4. Subir OT (LT23 Abiertas)", type=['csv', 'xlsx'])

if st.button("Procesar Datos y Analizar"):
    if archivo_mb52 and archivo_lx02 and archivo_nt and archivo_ot:
        try:
            # 1. Leer archivos
            df_mb52 = pd.read_csv(archivo_mb52) if archivo_mb52.name.endswith('.csv') else pd.read_excel(archivo_mb52)
            df_lx02 = pd.read_csv(archivo_lx02) if archivo_lx02.name.endswith('.csv') else pd.read_excel(archivo_lx02)
            df_nt = pd.read_csv(archivo_nt) if archivo_nt.name.endswith('.csv') else pd.read_excel(archivo_nt)
            df_ot = pd.read_csv(archivo_ot) if archivo_ot.name.endswith('.csv') else pd.read_excel(archivo_ot)
            
            # 2. Procesar MB52 (Stock MM en traslado por material)
            df_mb52['Trans./Trasl.'] = pd.to_numeric(df_mb52['Trans./Trasl.'], errors='coerce').fillna(0)
            df_mm = df_mb52[df_mb52['Trans./Trasl.'] > 0][['Material', 'Trans./Trasl.']].groupby('Material').sum().reset_index()

            # 3. Extraer listas de Documentos Abiertos Válidos
            nts_abiertas = set(pd.to_numeric(df_nt['Nº NT'], errors='coerce').dropna())
            ots_abiertas = set(pd.to_numeric(df_ot['Número de orden de transporte'], errors='coerce').dropna())

            # 4. Analizar LX02 (Tu mejora: El corazón del cruce)
            df_lx02['Tipo almacén'] = df_lx02['Tipo almacén'].astype(str)
            df_lx02['Stock disponible'] = pd.to_numeric(df_lx02['Stock disponible'], errors='coerce').fillna(0)
            df_lx02['Nº NT'] = pd.to_numeric(df_lx02['Nº NT'], errors='coerce').fillna(0)
            df_lx02['Ref_OT_Doc'] = pd.to_numeric(df_lx02['Número de orden de transporte'], errors='coerce').fillna(0)

            # Nos quedamos con el almacén transitorio (ej. 921) donde el stock no sea cero
            df_wm = df_lx02[(df_lx02['Tipo almacén'] == '921') & (df_lx02['Stock disponible'] != 0)].copy()

            # Clasificar cada línea de la LX02
            def clasificar_linea_wm(row):
                if row['Nº NT'] in nts_abiertas:
                    return 'Cant_Pendiente_NT'
                elif row['Ref_OT_Doc'] in ots_abiertas:
                    return 'Cant_Pendiente_OT'
                else:
                    return 'Cant_Fantasma_WM' # Está en 921 pero no tiene doc abierto

            df_wm['Estado_WM'] = df_wm.apply(clasificar_linea_wm, axis=1)

            # Sumar las cantidades (en valor absoluto porque en 921 suele figurar en negativo)
            df_wm['Stock disponible'] = df_wm['Stock disponible'].abs()
            df_wm_agrupado = df_wm.pivot_table(index='Material', columns='Estado_WM', values='Stock disponible', aggfunc='sum').fillna(0).reset_index()

            # Asegurar que existan las columnas para el cálculo
            for col in ['Cant_Pendiente_NT', 'Cant_Pendiente_OT', 'Cant_Fantasma_WM']:
                if col not in df_wm_agrupado.columns:
                    df_wm_agrupado[col] = 0

            # 5. Cruce Final (MM vs WM)
            resultado = pd.merge(df_mm, df_wm_agrupado, on='Material', how='left').fillna(0)

            # El stock justificado en WM es la suma de NTs y OTs válidas/abiertas
            resultado['WM_Justificado'] = resultado['Cant_Pendiente_NT'] + resultado['Cant_Pendiente_OT']
            
            # Lo que falta hacer 315 es lo que MM dice que está en traslado MENOS lo justificado en WM
            resultado['Falta_Hacer_315'] = resultado['Trans./Trasl.'] - resultado['WM_Justificado']

            def estado_final(row):
                if row['Falta_Hacer_315'] > 0:
                    return f"🚨 ERROR - Falta 315 (Faltan procesar {row['Falta_Hacer_315']} unidades)"
                elif row['Falta_Hacer_315'] < 0:
                    return "⚠️ ERROR - Diferencia Negativa (WM supera a MM)"
                else:
                    return "✅ OK - Pendiente de Picking (Coincide exacto)"

            resultado['Estado Final'] = resultado.apply(estado_final, axis=1)
            
            # Limpiar tabla para la vista final
            columnas_finales = ['Material', 'Trans./Trasl.', 'Cant_Pendiente_NT', 'Cant_Pendiente_OT', 'Falta_Hacer_315', 'Estado Final']
            resultado_vista = resultado[columnas_finales].rename(columns={'Trans./Trasl.': 'Stock_MM_Traslado'})

            st.success("¡Análisis completado con éxito!")
            
            # Mostrar la tabla en la pantalla con colores
            st.dataframe(resultado_vista, use_container_width=True)
            
            # Botón de descarga
            csv = resultado_vista.to_csv(index=False, encoding='utf-8-sig').encode('utf-8-sig')
            st.download_button(
                label="📥 Descargar Reporte Final en Excel/CSV",
                data=csv,
                file_name='Analisis_Traslados_Mejorado.csv',
                mime='text/csv',
            )
            
        except Exception as e:
            st.error(f"❌ Ocurrió un error procesando los archivos. Detalle: {e}")
    else:
        st.warning("⚠️ Por favor, subí los 4 archivos para comenzar.")