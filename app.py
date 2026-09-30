import io
import json
import os
import time
import pandas as pd
import streamlit as st
import google.generativeai as genai

st.set_page_config(
    page_title="Extractor IA: Formatos Manuscritos a Excel",
    page_icon="📝",
    layout="wide",
)

st.title("📝 Extractor de Formatos e Imágenes Manuscritas a Excel")
st.write(
    "Optimizado especialmente para leer formatos impresos con datos rellenados a mano."
)

with st.sidebar:
    st.header("Configuración")
    api_key = st.text_input(
        "Ingresa tu Gemini API Key:",
        type="password",
        help="Obtén tu clave en Google AI Studio",
    )

    modelos_disponibles = []

    if api_key.strip():
        try:
            genai.configure(api_key=api_key.strip())
            # Consultar modelos activos directamente asignados a la API Key
            for m in genai.list_models():
                if "generateContent" in m.supported_generation_methods:
                    modelos_disponibles.append(m.name)
        except Exception:
            pass

    if not modelos_disponibles:
        modelos_disponibles = [
            "models/gemini-1.5-flash",
            "models/gemini-1.5-pro",
            "models/gemini-2.0-flash-exp",
        ]

    modelo_seleccionado = st.selectbox(
        "Selecciona el Modelo de Gemini:",
        options=modelos_disponibles,
        index=0,
    )

    st.markdown("---")
    st.markdown(
        "**Consejos para mejor precisión:**\n"
        "• Asegúrate de que las fotos/escaneos tengan buena iluminación.\n"
        "• La imagen debe verse lo más derecha (alineada) posible.\n"
        "• Evita sombras fuertes sobre los trazos manuscritos."
    )


uploaded_file = st.file_uploader(
    "Selecciona el archivo (PDF o Imagen manuscrita)",
    type=["pdf", "png", "jpg", "jpeg"],
)

if uploaded_file is not None:
    st.info(
        f"Archivo cargado: **{uploaded_file.name}** ({round(uploaded_file.size / 1024, 2)} KB)"
    )

    if st.button("🚀 Extraer Datos Manuscritos", type="primary"):
        if not api_key:
            st.error("Por favor, ingresa tu API Key de Gemini en la barra lateral.")
        else:
            try:
                with st.spinner("Analizando trazos manuscritos y procesando..."):
                    genai.configure(api_key=api_key.strip())

                    documento_bytes = uploaded_file.getvalue()
                    mime_type = uploaded_file.type

                    cookie_file_part = {
                        "mime_type": mime_type,
                        "data": documento_bytes,
                    }

                    prompt = """
                    Este documento es un formato o formulario impreso cuyos campos han sido rellenados A MANO (manuscrito).
                    
                    INSTRUCCIONES DE EXTRACCIÓN MANUSCRITA:
                    1. Realiza una lectura minuciosa de cada campo impreso y su correspondiente valor escrito a mano.
                    2. Presta especial atención a los números escritos a mano (diferencia con cuidado 0, 6, 8, 1, 7, 3, 5).
                    3. Extrae TODOS los campos rellenados, tablas o listados sin omitir ninguna fila.
                    4. Si un texto a mano es parcialmente ilegible, transcribe tu mejor interpretación. Si el campo impreso está totalmente en blanco (sin escribir), déjalo como una cadena vacía "".
                    5. Devuelve ÚNICAMENTE un arreglo JSON de objetos donde cada objeto represente un registro/fila con sus respectivos campos impresos como llaves y lo manuscrito como valores.
                    """

                    model = genai.GenerativeModel(
                        model_name=modelo_seleccionado,
                        generation_config={
                            "response_mime_type": "application/json",
                            "temperature": 0.0,
                        },
                    )

                    response = model.generate_content([cookie_file_part, prompt])

                    texto_respuesta = response.text.strip()
                    if texto_respuesta.startswith("```json"):
                        texto_respuesta = texto_respuesta[7:]
                    if texto_respuesta.startswith("```"):
                        texto_respuesta = texto_respuesta[3:]
                    if texto_respuesta.endswith("```"):
                        texto_respuesta = texto_respuesta[:-3]
                    texto_respuesta = texto_respuesta.strip()

                    datos_json = json.loads(texto_respuesta)

                    if isinstance(datos_json, list):
                        df = pd.DataFrame(datos_json)
                    elif isinstance(datos_json, dict):
                        listas = [
                            v for v in datos_json.values() if isinstance(v, list)
                        ]
                        if listas:
                            df = pd.DataFrame(listas[0])
                        else:
                            df = pd.DataFrame([datos_json])
                    else:
                        df = pd.DataFrame([datos_json])

                    st.success("¡Extracción de datos manuscritos completada!")
                    st.subheader("Vista Previa de los Datos")

                    st.dataframe(df, use_container_width=True)

                    output_excel = io.BytesIO()
                    with pd.ExcelWriter(
                        output_excel, engine="openpyxl"
                    ) as writer:
                        df.to_excel(
                            writer, index=False, sheet_name="Datos Manuscritos"
                        )
                    excel_data = output_excel.getvalue()

                    st.download_button(
                        label="📥 Descargar Excel (.xlsx)",
                        data=excel_data,
                        file_name=f"{os.path.splitext(uploaded_file.name)[0]}_manuscrito.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    )

            except Exception as e:
                st.error(f"❌ Error devuelto directamente por la API: {e}")

st.markdown("---")
st.caption("💻 **Sistema de Extractor IA** | Diseñado y desarrollado por **Alam E.T.N.**")