import io
import json
import os
import tempfile
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

    # Inclusión de opciones Flash y Pro en el selector
    modelo_seleccionado = st.selectbox(
        "Selecciona el Modelo de Gemini:",
        options=["gemini-3.6-flash", "gemini-3.1-pro-preview"],
        index=0,
        help=(
            "• gemini-3.6-flash: Rápido y ligero para uso cotidiano (Gratuito).  \n\n"
            "• gemini-3.1-pro-preview: Modelo Pro con razonamiento avanzado (De Paga - API con Facturacion Activa)."
        ),
    )

    st.markdown("---")
    st.markdown(
        "**Consejos para mejor precisión:**\n"
        "• Asegúrate de que las fotos/escaneos tengan buena iluminación.\n"
        "• La imagen debe verse lo más derecha (alineada) posible.\n"
        "• Evita sombras fuertes sobre los trazos manuscritos."
    )

def generar_contenido_manuscrito(client, modelo, archivo, prompt):
    """Maneja el límite de cuotas (429) y saturación (503) esperando los segundos necesarios."""
    max_reintentos = 3

    for intento in range(max_reintentos):
        try:
            response = client.models.generate_content(
                model=modelo,
                contents=[archivo, prompt],
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
            if e.code in [429, 503] or "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                tiempo_espera = 10 * (intento + 1)  # Espera 10s, 20s, 30s
                st.warning(
                    f"⏳ Límite de cuota alcanzado o servidor ocupado. Esperando {tiempo_espera}s para reintentar... (Intento {intento + 1}/{max_reintentos})"
                )
                time.sleep(tiempo_espera)
            else:
                raise e
        except Exception as e:
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e) or "503" in str(e):
                tiempo_espera = 10 * (intento + 1)
                st.warning(
                    f"⏳ Reintentando conexión por cuota agotada ({tiempo_espera}s)..."
                )
                time.sleep(tiempo_espera)
            else:
                raise e

    raise Exception(
        "Se ha excedido el límite diario de peticiones gratuitas de esta API Key. Por favor ingresa una API Key nueva en la barra lateral."
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
            st.error(
                "Por favor, ingresa tu API Key de Gemini en la barra lateral."
            )
        else:
            tmp_file_path = None
            try:
                with st.spinner(
                    "Analizando trazos manuscritos y convirtiendo a datos estructurados..."
                ):
                    # 1. Escritura segura y aislamiento del archivo temporal
                    suffix = os.path.splitext(uploaded_file.name)[1]
                    with tempfile.NamedTemporaryFile(
                        delete=False, suffix=suffix
                    ) as tmp_file:
                        tmp_file.write(uploaded_file.getvalue())
                        tmp_file_path = tmp_file.name

                    client = genai.Client(api_key=api_key)

                    # 2. Subida del archivo con captura de error independiente
                    try:
                        archivo_gemini = client.files.upload(file=tmp_file_path)
                    except Exception as upload_err:
                        st.error(f"Error al cargar el archivo en los servidores de Google: {upload_err}")
                        st.stop()

                    # Prompt diseñado específicamente para OCR manuscrito en formatos
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
                        client, modelo_seleccionado, archivo_gemini, prompt
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

                    st.dataframe(df, width="stretch")

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

            finally:
                # Limpieza garantizada del archivo temporal
                if tmp_file_path and os.path.exists(tmp_file_path):
                    try:
                        os.remove(tmp_file_path)
                    except Exception:
                        pass


st.markdown("---")
st.caption("💻 **Sistema de Extractor IA** | Diseñado y desarrollado por **Alam E.T.N.**")