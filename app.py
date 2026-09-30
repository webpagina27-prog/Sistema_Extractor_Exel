import io
import json
import os
import pandas as pd
import streamlit as st
import google.generativeai as genai
from google.api_core import exceptions

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

    # Lista verificada de modelos de 'Texto de salida' con cuota gratuita activa (20 o 500 RPD)
    # Ordenados por precisión de lectura y razonamiento manuscrito
    modelos_aprobados = [
        "models/gemini-3.8-flash",      # Principal (Mayor precisión en OCR y razonamiento)
        "models/gemini-3.7-flash",      # Respaldo 1 (20 RPD)
        "models/gemini-3.6-flash",      # Respaldo 2 (20 RPD)
        "models/gemini-3.5-flash",      # Respaldo 3 (20 RPD)
        "models/gemini-3-flash",        # Respaldo 4 (20 RPD)
        "models/gemini-2.5-flash",      # Respaldo 5 (20 RPD)
        "models/gemini-3.5-flash-lite", # Alto volumen (500 RPD)
        "models/gemini-3.1-flash-lite", # Alto volumen (500 RPD)
        "models/gemini-2.5-flash-lite", # Respaldo Lite (20 RPD)
    ]

    modelos_disponibles = []

    if api_key.strip():
        try:
            genai.configure(api_key=api_key.strip())
            
            # Consultamos los modelos disponibles en la cuenta de la API
            modelos_api = [
                m.name for m in genai.list_models()
                if "generateContent" in m.supported_generation_methods
            ]
            
            # Filtramos dejando SOLO los que están en nuestra lista de cuota gratuita activa
            for mod in modelos_aprobados:
                if mod in modelos_api:
                    modelos_disponibles.append(mod)

        except Exception:
            pass

    # Si la API no ha respondido o no hay clave, usamos la lista predefinida limpia
    if not modelos_disponibles:
        modelos_disponibles = modelos_aprobados

    # Nos aseguramos de que gemini-3.8-flash SIEMPRE quede fijo en el primer lugar (índice 0)
    if "models/gemini-3.8-flash" in modelos_disponibles:
        modelos_disponibles.remove("models/gemini-3.8-flash")
        modelos_disponibles.insert(0, "models/gemini-3.8-flash")

    modelo_seleccionado = st.selectbox(
        "Selecciona el Modelo de Gemini:",
        options=modelos_disponibles,
        index=0,
        key="selector_modelo_gemini",
        help="Si agotas las peticiones diarias de un modelo (Error 429), cambia a otro de la lista para continuar de inmediato."
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
        if not api_key.strip():
            st.error("Por favor, ingresa tu API Key de Gemini en la barra lateral.")
        else:
            try:
                nombre_modelo_corto = modelo_seleccionado.replace("models/", "")
                with st.spinner(f"Analizando trazos manuscritos con {nombre_modelo_corto}..."):
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

            except exceptions.ResourceExhausted as e:
                # Captura específica de cuota alcanzada (Error 429 / Rate Limit)
                st.error(
                    f"🛑 **Cuota agotada para el modelo `{modelo_seleccionado}`.**\n\n"
                    "Has alcanzado el límite diario (o por minuto) de este modelo específico.\n\n"
                    "👉 **Solución inmediata:** En el menú desplegable de la barra lateral, "
                    "**selecciona otro modelo disponible** (por ejemplo: `gemini-3.7-flash` o `gemini-3.5-flash-lite`) "
                    "y vuelve a presionar el botón para continuar sin esperar."
                )
            except Exception as e:
                err_msg = str(e)
                if "429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg:
                    st.error(
                        f"🛑 **Cuota agotada para el modelo `{modelo_seleccionado}`.**\n\n"
                        "👉 **Solución inmediata:** Selecciona otro modelo en el desplegable "
                        "de la barra lateral para continuar trabajando gratis."
                    )
                else:
                    st.error(f"❌ Error devuelto por la API: {e}")

st.markdown("---")
st.caption("💻 **Sistema de Extractor IA** | Diseñado y desarrollado por **Alam E.T.N.**")