import os
import subprocess
from PIL import Image, ImageFont, ImageDraw
from dotenv import load_dotenv

FORMAT_OUTPUT = ".epub"

load_dotenv()

# Carpeta que Calibre-Web-Automated vigila para importar libros nuevos
# automáticamente a la biblioteca. Se monta como volumen compartido entre
# el contenedor del bot y el contenedor de CWA (ver docker-compose.yml).
CWA_INGEST_DIR = os.getenv("CWA_INGEST_DIR", "cwa-ingest")
os.makedirs(CWA_INGEST_DIR, exist_ok=True)


CONVERTED_DIR = "books/converted"
os.makedirs(CONVERTED_DIR, exist_ok=True)


class CalibreError(Exception):
    """Excepción base para errores relacionados con Calibre."""

    pass


class ConversionError(CalibreError):
    """Excepción lanzada cuando falla la conversión de un archivo."""

    pass


class FanficProcessingError(CalibreError):
    """Excepción lanzada cuando falla el procesamiento de un FanFic."""

    pass


def convert_to_epub(book_path: str, name_book: str, output_dir: str = CONVERTED_DIR):
    try:
        output = f"{output_dir}/{name_book}{FORMAT_OUTPUT}"
        subprocess.run(["ebook-convert", f"{book_path}", f"{output}"], check=True)
    except subprocess.CalledProcessError as e:
        raise ConversionError(f"Error al convertir el archivo: {e}")
    return output


async def send_to_library(book_file, book_name: str):
    """Descarga el archivo directo a la carpeta de ingest de CWA, sin
    ninguna conversión. Calibre-Web-Automated lo recoge automáticamente
    y lo agrega a la biblioteca."""
    try:
        destination = f"{CWA_INGEST_DIR}/{book_name}"
        await book_file.download_to_drive(destination)
    except Exception as e:
        raise ConversionError(f"Error al enviar el archivo a la biblioteca: {e}")
    return destination


def tranform_fanfic(fanfic_file: str, name_fanfic: str):
    try:
        with open(fanfic_file, "r", encoding="utf-8", errors="ignore") as base_file:
            content = base_file.read()

        start_index = content.find("<!-- END navigation -->")
        end_index = content.find("<!-- END work -->")

        if start_index == -1 or end_index == -1:
            raise FanficProcessingError(
                "No se encontraron los marcadores de inicio o fin en el archivo."
            )

        subcontent = content[start_index:end_index]
        modified_subcontent = subcontent.replace("Texto del capítulo", "Capítulo")

        transform_path = f"books/random/{name_fanfic}.html"

        with open(transform_path, "w", encoding="utf-8") as modified_file:
            modified_file.write(modified_subcontent)

        list_name = name_fanfic.split("-")
        serie = insert_jump(list_name[2][0 : list_name[2].find("[")], "\n", 3)
        title = insert_jump(list_name[0], "\n", 3)

        modified_name = title + "-" + serie
        other_name = modified_name.replace("\n", "").replace("\r", "")

        modified_path = convert_to_epub(
            transform_path, other_name, output_dir=CWA_INGEST_DIR
        )
        metedata_fanfic(modified_path, name_fanfic)
        manage_covert(modified_path, modified_name, True)

    except FileNotFoundError:
        raise FanficProcessingError(
            f"Error: El archivo '{fanfic_file}' no fue encontrado."
        )
    except IOError as e:
        raise FanficProcessingError(f"Error de E/S al manejar el archivo: {e}")
    except ValueError as e:
        raise FanficProcessingError(f"Error en el contenido del archivo: {e}")
    except Exception as e:
        raise FanficProcessingError(f"Ocurrió un error inesperado: {e}")
    return None


def metedata_fanfic(fanfic_path: str, name_fanfic: str):
    try:
        list_file_name = name_fanfic.split("-")
        series = list_file_name[2][0 : list_file_name[2].find("[")]

        subprocess.run(
            [
                "ebook-meta",
                fanfic_path,
                "-a",
                list_file_name[1],
                "-t",
                list_file_name[0],
                "--tags",
                "FanFiction",
                "-p",
                "Archive of Our Own",
                "-s",
                series,
            ]
        )
    except subprocess.CalledProcessError as e:
        print(e.output)
    return None


def manage_covert(book_path: str, name_book: str, fanfic: bool = False):
    if fanfic:
        imagen_base = Image.open("templ/default.jpg")
        dibujo = ImageDraw.Draw(imagen_base)

        try:
            fuente = ImageFont.truetype(
                "templ/FiraSans-SemiBoldItalic.ttf", 43
            )  # Cambia "arial.ttf" por la ruta a tu fuente
        except IOError:
            fuente = ImageFont.load_default()

        texto = name_book.replace("-", "\n")
        texto = "   " + texto

        posicion = (300, 300)

        # Color del texto (en formato RGB)
        color_texto = (0, 0, 0)  # Blanco

        dibujo.text(posicion, texto, font=fuente, fill=color_texto, anchor="mm")

        path_image = f"coverts/{name_book}.jpg"
        imagen_base.save(path_image)

        subprocess.run(["ebook-meta", book_path, "--cover", path_image])
    else:
        path_image = f"coverts/{name_book}.jpg"

        subprocess.run(["ebook-meta", book_path, "--get-cover", path_image])

        imagen = Image.open(path_image)
        ancho, alto = imagen.size

        if not (ancho == 600 and alto == 900):
            img_resize = imagen.resize((600, 900))
            img_resize.save(path_image)

            subprocess.run(["ebook-meta", book_path, "--cover", path_image])

    return None


def get_name(book_path: str, fanfic: bool = False):
    if fanfic:
        start_index = book_path.rfind("/")
        book_name = book_path[start_index + 1 : len(book_path)]
    else:
        start_index = book_path.rfind("/")
        end_index = book_path.rfind(".")
        book_name = book_path[start_index + 1 : end_index]
    return book_name


def insert_jump(cadena: str, caracter: str, cada: int):
    palabras = cadena.split()

    resultado = []
    for i in range(0, len(palabras), cada):
        resultado.append(" ".join(palabras[i : i + cada]))

    return caracter.join(resultado)


if __name__ == "__main__":
    # book = 'books/random/raw/Bonable - Anónimo - Little Witch Academia [Archivo propio]'
    # name = 'Bonable - Anónimo - Little Witch Academia [Archivo propio]'
    # convert_to_epub(book, name)
    # tranform_fanfic(book, name)
    # manage_covert(new_book, "Aqui estoy - Jonathan Safran Foer")
    pass
