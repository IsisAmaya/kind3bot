import os
import re
import html
from email import policy
from email.parser import BytesParser
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


def _extract_ao3_metadata(content: str) -> tuple[str, str, str]:
    """Read title, author, and series from an AO3 downloaded HTML page."""
    title_match = re.search(
        r'<h2[^>]*class=["\'][^"\']*\btitle\b[^"\']*["\'][^>]*>(.*?)</h2>',
        content,
        re.IGNORECASE | re.DOTALL,
    )
    if not title_match:
        raise FanficProcessingError("No se encontró el título en el HTML de AO3.")
    title = html.unescape(re.sub(r"<[^>]+>", " ", title_match.group(1)))
    title = re.sub(r"\s+", " ", title).strip()

    author_match = re.search(
        r'<a[^>]*rel=["\']author["\'][^>]*>(.*?)</a>',
        content,
        re.IGNORECASE | re.DOTALL,
    )
    author = "Anonymous" if not author_match else html.unescape(
        re.sub(r"<[^>]+>", " ", author_match.group(1))
    )
    author = re.sub(r"\s+", " ", author).strip()
    if not author:
        author = "Anonymous"

    series_match = re.search(
        r'<dd[^>]*class=["\'][^"\']*\bseries\b[^"\']*["\'][^>]*>(.*?)</dd>',
        content,
        re.IGNORECASE | re.DOTALL,
    )
    series = "" if not series_match else series_match.group(1)
    if series:
        series_link = re.search(r"<a\b[^>]*>(.*?)</a>", series, re.IGNORECASE | re.DOTALL)
        if series_link:
            series = series_link.group(1)
    series = html.unescape(re.sub(r"<[^>]+>", " ", series))
    series = re.sub(r"\s+", " ", series).strip()

    # Browser-saved AO3 MHT pages preserve the original command metadata in
    # the document title: "Work title - Author - Fandom [extra]". Prefer it
    # over AO3's series block, which describes a collection rather than fandom.
    document_title = re.search(r"<title[^>]*>(.*?)</title>", content, re.I | re.S)
    if document_title:
        title_parts = html.unescape(
            re.sub(r"\s+", " ", document_title.group(1))
        ).strip().split(" - ", 2)
        if len(title_parts) == 3:
            title, author, series = (part.strip() for part in title_parts)

    return title, author, series


def tranform_fanfic(fanfic_file: str, name_fanfic: str | None = None):
    try:
        with open(fanfic_file, "rb") as base_file:
            raw_content = base_file.read()
        if fanfic_file.lower().endswith((".mht", ".mhtml")):
            message = BytesParser(policy=policy.default).parsebytes(raw_content)
            html_part = next(
                (part for part in message.walk() if part.get_content_type() == "text/html"),
                None,
            )
            if html_part is None:
                raise FanficProcessingError("El archivo MHT no contiene una página HTML.")
            html_bytes = html_part.get_payload(decode=True)
            charset_match = re.search(
                rb"charset\s*=\s*[\"']?([\w.-]+)", html_bytes[:4096], re.IGNORECASE
            )
            charset = charset_match.group(1).decode("ascii") if charset_match else "utf-8"
            content = html_bytes.decode(charset, errors="replace")
        else:
            content = raw_content.decode("utf-8", errors="replace")

        title, author, series = _extract_ao3_metadata(content)
        source_name = name_fanfic or os.path.splitext(os.path.basename(fanfic_file))[0]
        if name_fanfic and " - " in name_fanfic:
            # Preserve the old API for callers that still pass metadata.
            parts = name_fanfic.split("-", 2)
            if len(parts) == 3:
                title, author, series = (part.strip() for part in parts)
        if not series:
            series = title

        start_index = content.find("<!-- END navigation -->")
        end_index = content.find("<!-- END work -->")

        if start_index == -1 or end_index == -1:
            raise FanficProcessingError(
                "No se encontraron los marcadores de inicio o fin en el archivo."
            )

        subcontent = content[start_index:end_index]
        modified_subcontent = subcontent.replace("Texto del capítulo", "Capítulo")

        transform_dir = "books/random"
        os.makedirs(transform_dir, exist_ok=True)
        transform_path = os.path.join(transform_dir, f"{source_name}.html")

        with open(transform_path, "w", encoding="utf-8") as modified_file:
            modified_file.write(modified_subcontent)

        serie = insert_jump(series, "\n", 3)
        title = insert_jump(title, "\n", 3)

        modified_name = title + "-" + serie
        other_name = re.sub(r"[\\/:*?\"<>|\n\r]+", " ", modified_name)
        other_name = re.sub(r"\s+", " ", other_name).strip(" .")

        modified_path = convert_to_epub(
            transform_path, other_name, output_dir=CWA_INGEST_DIR
        )
        metedata_fanfic(modified_path, title.replace("\n", " "), author, series)
        try:
            manage_covert(modified_path, modified_name, True)
        except Exception as e:
            raise FanficProcessingError(f"No se pudo generar la portada: {e}")

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


def metedata_fanfic(fanfic_path: str, title: str, author: str, series: str):
    try:
        subprocess.run(
            [
                "ebook-meta",
                fanfic_path,
                "-a",
                author,
                "-t",
                title,
                "--tags",
                "FanFiction",
                "-p",
                "Archive of Our Own",
                "-s",
                series,
            ],
            check=True,
        )
    except subprocess.CalledProcessError as e:
        raise FanficProcessingError(f"No se pudieron guardar los metadatos: {e}")
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
