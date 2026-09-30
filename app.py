import io
import json
import os
import time
import pandas as pd
import streamlit as st
from google import genai
from google.genai import types
from google.genai.errors import APIError

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

    modelo_seleccionado = st.selectbox(
        "Selecciona el Modelo de Gemini:",
        options=["gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-pro"],
        index=0,
        help=(
            "• gemini-2.0-flash: Modelo rápido y preciso de última generación (Gratuito).  \n\n"
            "• gemini-1.5-flash: Alternativa estable y ligera.  \n\n"
            "• gemini-1.5-pro: Razonamiento avanzado para letras manuscritas complejas."
        ),
    )

    st.markdown("---")
    st.markdown(
        "**Consejos para mejor precisión:**\n"
        "• Asegúrate de que las fotos/escaneos tengan buena iluminación.\n"
        "• La imagen debe verse lo más derecha (alineada) posible.\n"
        "• Evita sombras fuertes sobre los trazos manuscritos."
    )


def generar_contenido_manuscrito(client, modelo, archivo_part, prompt):
    """Ejecuta la extracción enviando el documento directo en memoria."""
    max_reintentos = 3

    for intento in range(max_reintentos):
        try:
            response = client.models.generate_content(
                model=modelo,
                contents=[archivo_part, prompt],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.0,
                    tools=[],
                    automatic_function_calling=types.AutomaticFunctionCallingConfig(
                        disable=True
                    ),
                ),
            )
            return response
        except APIError as e:
            # Si el error es por modelo no encontrado, detenemos reintentos inútiles
            if "NOT_FOUND" in str(e) or e.code == 404:
                st.error(f"❌ El modelo `{modelo}` no está disponible en la API. Selecciona otro en la barra lateral.")
                st.stop()
            elif "RESOURCE_EXHAUSTED" in str(e) or e.code == 429:
                st.error(
                    "🛑 **Límite diario alcanzado en esta API Key (capa gratuita agotada).**  \n"
                    "Por favor ingresa una API Key diferente en la barra lateral para continuar."
                )
                st.stop()
            elif e.code == 503 or "503" in str(e):
                tiempo_espera = (intento + 1) * 5
                st.warning(
                    f"Servidor ocupado. Reintentando en {tiempo_espera}s... (Intento {intento + 1}/{max_reintentos})"
                )
                time.sleep(tiempo_espera)
            else:
                raise e
        except Exception as e:
            if "RESOURCE_EXHAUSTED" in str(e) or "429" in str(e):
                st.error("🛑 **Cuota diaria agotada.** Cambia la clave en la barra lateral.")
                st.stop()
            elif "503" in str(e) or "UNAVAILABLE" in str(e):
                tiempo_espera = (intento + 1) * 5
                st.warning(f"Servidor saturado. Reintentando en {tiempo_espera}s...")
                time.sleep(tiempo_espera)
            else:
                raise e

    raise Exception("El servidor no respondió tras los reintentos.")


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
            st.error(
                "Por favor, ingresa tu API Key de Gemini en la barra lateral."
            )
        else:
            try:
                with st.spinner(
                    "Analizando trazos manuscritos y convirtiendo a datos estructurados..."
                ):
                    client = genai.Client(api_key=api_key)

                    documento_bytes = uploaded_file.getvalue()
                    mime_type = uploaded_file.type

                    archivo_part = types.Part.from_bytes(
                        data=documento_bytes,
                        mime_type=mime_type
                    )

                    prompt = """
                    Este documento es un formato o formulario impreso cuyos campos han sido rellenados A MANO (manuscrito).
                    
                    INSTRUCCIONES DE EXTRACCIÓN MANUSCRITA:
                    1. Realiza una lectura minuciosa de cada campo impreso y su correspondiente valor escrito a mano.
                    2. Presta especial atención a los números escritos a mano (diferencia con cuidado 0, 6, 8, 1, 7, 3, 5).
                    3. Extrae TODOS los campos rellenados, tablas o listados sin omitir ninguna fila.
                    4. Si un texto a mano es parcialmente ilegible, transcribe tu mejor interpretación. Si el campo impreso está totalmente en blanco (sin escribir), déjalo como una cadena vacía "".
                    5. Devuelve ÚNICAMENTE un arreglo JSON de objetos donde cada objeto represente un registro/fila con sus respectivos campos impresos como llaves y lo manuscrito como valores.
                    """

                    response = generar_contenido_manuscrito(
                        client, modelo_seleccionado, archivo_part, prompt
                    )

                    datos_json = json.loads(response.text)

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
                st.error(f"Error durante el procesamiento: {e}")


st.markdown("---")
st.caption("💻 **Sistema de Extractor IA** | Diseñado y desarrollado por **Alam E.T.N.**")