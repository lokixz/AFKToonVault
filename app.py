from __future__ import annotations

import re
import threading
import zipfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import requests
import webview
from bs4 import BeautifulSoup
from PIL import Image


APP_NAME = "AFK Labs ToonVault"
ROOT = Path(__file__).resolve().parent
WEB_DIR = ROOT / "web"
INDEX_HTML = WEB_DIR / "index.html"
MAX_SINGLE_IMAGE_HEIGHT = 30000


def clean_filename(value: str) -> str:
    value = re.sub(r'[<>:"/\\|?*\x00-\x1F]', "", value).strip()
    return value or "chapter"


def parse_webtoon_url(raw_url: str) -> Optional[Dict[str, str]]:
    raw_url = raw_url.strip()
    if not raw_url:
        return None

    parsed = urlparse(raw_url)
    query = parse_qs(parsed.query)
    parts = [part for part in parsed.path.split("/") if part]

    if parsed.scheme not in {"http", "https"}:
        return None
    if parsed.netloc.lower() != "www.webtoons.com":
        return None
    if "title_no" not in query:
        return None
    if len(parts) < 4 or parts[3].lower() != "list":
        return None

    return {
        "url": raw_url,
        "name": clean_filename(parts[2].replace("-", " ").title()),
        "slug": parts[2],
    }


def normalize_list_page(url: str, page: int) -> str:
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    query["page"] = [str(page)]
    flat_query = []
    for key, values in query.items():
        for value in values:
            flat_query.append((key, value))
    return urlunparse(parsed._replace(query=urlencode(flat_query)))


class ToonVaultApi:
    def __init__(self) -> None:
        self.queue: List[Dict[str, str]] = []
        self.lock = threading.Lock()
        self.worker: Optional[threading.Thread] = None
        self.state = {
            "active": False,
            "status": "Pronto para iniciar.",
            "progress": 0,
            "logs": ["AFK Labs ToonVault iniciado."],
            "error": "",
        }

    def add_urls(self, text: str) -> Dict[str, object]:
        added = []
        ignored = []

        with self.lock:
            queued_slugs = {item["slug"] for item in self.queue}
            for line in text.splitlines():
                parsed = parse_webtoon_url(line)
                if not parsed:
                    if line.strip():
                        ignored.append(line.strip())
                    continue

                if parsed["slug"] in queued_slugs:
                    ignored.append(parsed["url"])
                    continue

                item = {
                    "id": f"q{len(self.queue) + len(added) + 1}_{parsed['slug']}",
                    "name": parsed["name"],
                    "slug": parsed["slug"],
                    "url": parsed["url"],
                    "start": "1",
                    "end": "end",
                }
                self.queue.append(item)
                queued_slugs.add(parsed["slug"])
                added.append(item)

        self.log(f"{len(added)} link(s) adicionados. {len(ignored)} ignorado(s).")
        return {"queue": self.get_queue(), "added": added, "ignored": ignored}

    def get_queue(self) -> List[Dict[str, str]]:
        with self.lock:
            return [dict(item) for item in self.queue]

    def update_queue(self, rows: List[Dict[str, str]]) -> Dict[str, object]:
        with self.lock:
            by_id = {row.get("id"): row for row in rows}
            for item in self.queue:
                row = by_id.get(item["id"])
                if not row:
                    continue
                item["start"] = str(row.get("start", "1")).strip() or "1"
                item["end"] = str(row.get("end", "end")).strip() or "end"
        return {"queue": self.get_queue()}

    def remove_item(self, item_id: str) -> Dict[str, object]:
        with self.lock:
            self.queue = [item for item in self.queue if item["id"] != item_id]
        return {"queue": self.get_queue()}

    def clear_queue(self) -> Dict[str, object]:
        with self.lock:
            self.queue.clear()
        self.log("Fila limpa.")
        return {"queue": self.get_queue()}

    def choose_folder(self) -> str:
        folder = webview.windows[0].create_file_dialog(webview.FOLDER_DIALOG)
        if not folder:
            return ""
        if isinstance(folder, (list, tuple)):
            return folder[0] if folder else ""
        return str(folder)

    def start_download(self, options: Dict[str, object]) -> Dict[str, object]:
        with self.lock:
            if self.state["active"]:
                return {"ok": False, "message": "Um download ja esta em andamento."}
            queue = [dict(item) for item in self.queue]

        valid, message = self.validate_job(queue, options)
        if not valid:
            self.set_state(status=message, error=message)
            return {"ok": False, "message": message}

        self.worker = threading.Thread(
            target=self.run_download_job,
            args=(queue, dict(options)),
            daemon=True,
        )
        self.worker.start()
        return {"ok": True, "message": "Download iniciado."}

    def get_state(self) -> Dict[str, object]:
        with self.lock:
            return dict(self.state)

    def validate_job(self, queue: List[Dict[str, str]], options: Dict[str, object]) -> Tuple[bool, str]:
        save_path = str(options.get("savePath", "")).strip()
        if not queue:
            return False, "Adicione pelo menos uma obra na fila."
        if not save_path or not Path(save_path).exists():
            return False, "Selecione uma pasta valida para salvar."

        for item in queue:
            try:
                start = int(item["start"])
            except ValueError:
                return False, f"Inicio invalido em {item['name']}."

            if start < 1:
                return False, f"Inicio precisa ser maior que zero em {item['name']}."

            if item["end"].lower() != "end":
                try:
                    end = int(item["end"])
                except ValueError:
                    return False, f"Fim invalido em {item['name']}."
                if end < start:
                    return False, f"Fim precisa ser maior ou igual ao inicio em {item['name']}."

        return True, "ok"

    def run_download_job(self, queue: List[Dict[str, str]], options: Dict[str, object]) -> None:
        self.set_state(active=True, progress=0, error="", status="Preparando download...")
        self.log("Download iniciado.")

        try:
            save_root = Path(str(options["savePath"]))
            save_as = str(options.get("saveAs", "pdf"))
            group_by_comic = bool(options.get("groupByComic", True))
            group_by_chapter = bool(options.get("groupByChapter", False))

            total_items = len(queue)
            for index, item in enumerate(queue, start=1):
                self.set_state(status=f"Lendo capitulos de {item['name']}...")
                chapters = self.fetch_chapters(item["url"])
                selected = self.select_chapters(chapters, item["start"], item["end"])
                if not selected:
                    self.log(f"Nenhum capitulo selecionado para {item['name']}.")
                    continue

                base_path = save_root / clean_filename(item["name"]) if group_by_comic else save_root
                base_path.mkdir(parents=True, exist_ok=True)

                for chapter_index, chapter in enumerate(selected, start=1):
                    chapter_number = chapters.index(chapter) + 1
                    chapter_label = clean_filename(f"({chapter_number}) {chapter['title']}")
                    self.set_state(status=f"Baixando {item['name']} - capitulo {chapter_number}")
                    chapter_dir = base_path / chapter_label
                    chapter_dir.mkdir(parents=True, exist_ok=True)
                    image_files = self.download_chapter_images(chapter, chapter_dir, item["slug"], chapter_number)

                    if save_as == "pdf":
                        self.export_pdf(image_files, base_path / f"{chapter_label}.pdf")
                        self.delete_temp_images(chapter_dir)
                    elif save_as == "cbz":
                        self.export_cbz(image_files, base_path / f"{chapter_label}.cbz")
                        self.delete_temp_images(chapter_dir)
                    elif save_as == "single":
                        self.export_single_image(image_files, base_path / f"{chapter_label}.png")
                        self.delete_temp_images(chapter_dir)
                    elif not group_by_chapter:
                        for file_path in image_files:
                            target = base_path / file_path.name
                            if target != file_path:
                                file_path.replace(target)
                        self.delete_temp_images(chapter_dir)

                    percent = int(((index - 1) + chapter_index / len(selected)) / total_items * 100)
                    self.set_state(progress=max(0, min(100, percent)))

            self.set_state(active=False, progress=100, status="Concluido.")
            self.log("Download concluido.")
        except Exception as exc:
            self.set_state(active=False, error=str(exc), status=f"Erro: {exc}")
            self.log(f"Erro: {exc}")

    def fetch_chapters(self, url: str) -> List[Dict[str, str]]:
        session = requests.Session()
        session.headers.update({"Cookie": "pagGDPR=true;", "User-Agent": "Mozilla/5.0"})

        chapters: List[Dict[str, str]] = []
        seen_urls = set()
        max_pages = 120

        for page in range(1, max_pages + 1):
            self.set_state(status=f"Lendo pagina {page} da lista...")
            page_url = normalize_list_page(url, page)
            response = session.get(page_url, timeout=30)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            list_node = soup.find(id="_listUl")
            if not list_node:
                break

            page_chapters = []
            episode_numbers = []
            for li in list_node.find_all("li"):
                link = li.find("a", href=True)
                if not link:
                    continue
                href = link["href"]
                episode_no = li.get("data-episode-no") or ""
                if episode_no.isdigit():
                    episode_numbers.append(int(episode_no))
                title_node = li.select_one(".subj span") or li.select_one(".subj")
                title = title_node.get_text(" ", strip=True) if title_node else link.get_text(" ", strip=True)
                page_chapters.append({"url": href, "title": clean_filename(title)})

            if not page_chapters:
                break
            new_chapters = [chapter for chapter in page_chapters if chapter["url"] not in seen_urls]
            if not new_chapters:
                break

            if page == 1 and episode_numbers:
                per_page = max(len(page_chapters), 1)
                max_pages = min(max_pages, (max(episode_numbers) + per_page - 1) // per_page + 2)

            for chapter in new_chapters:
                seen_urls.add(chapter["url"])
            chapters.extend(new_chapters)

        chapters.reverse()
        if not chapters:
            raise RuntimeError("Nenhum capitulo encontrado. Verifique o link.")
        return chapters

    def select_chapters(self, chapters: List[Dict[str, str]], start: str, end: str) -> List[Dict[str, str]]:
        start_index = max(int(start) - 1, 0)
        end_index = len(chapters) if end.lower() == "end" else min(int(end), len(chapters))
        return chapters[start_index:end_index]

    def download_chapter_images(
        self,
        chapter: Dict[str, str],
        chapter_dir: Path,
        slug: str,
        chapter_number: int,
    ) -> List[Path]:
        session = requests.Session()
        session.headers.update({"Cookie": "pagGDPR=true;", "Referer": chapter["url"]})
        response = session.get(chapter["url"], timeout=30)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        images = soup.select("#_imageList img")
        if not images:
            raise RuntimeError(f"Nenhuma imagem encontrada em {chapter['title']}.")

        files: List[Path] = []
        for index, image in enumerate(images, start=1):
            image_url = image.get("data-url") or image.get("src")
            if not image_url:
                continue
            self.set_state(status=f"Baixando imagem {index}/{len(images)} do capitulo {chapter_number}")
            image_response = session.get(image_url, timeout=45)
            image_response.raise_for_status()
            file_path = chapter_dir / f"{clean_filename(slug)} Ch{chapter_number}.{index:03d}.jpg"
            file_path.write_bytes(image_response.content)
            files.append(file_path)

        if not files:
            raise RuntimeError(f"Nenhuma imagem baixada em {chapter['title']}.")
        return files

    def export_pdf(self, image_files: List[Path], output_path: Path) -> None:
        opened = [Image.open(file_path).convert("RGB") for file_path in image_files]
        try:
            first, rest = opened[0], opened[1:]
            first.save(output_path, "PDF", resolution=100.0, save_all=True, append_images=rest)
        finally:
            for image in opened:
                image.close()

    def export_cbz(self, image_files: List[Path], output_path: Path) -> None:
        with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as archive:
            for file_path in image_files:
                archive.write(file_path, file_path.name)

    def export_single_image(self, image_files: List[Path], output_path: Path) -> None:
        opened = [Image.open(file_path).convert("RGB") for file_path in image_files]
        try:
            width = max(image.width for image in opened)
            height = sum(image.height for image in opened)
            canvas = Image.new("RGB", (width, height), "white")
            top = 0
            for image in opened:
                canvas.paste(image, (0, top))
                top += image.height

            if canvas.height > MAX_SINGLE_IMAGE_HEIGHT:
                ratio = MAX_SINGLE_IMAGE_HEIGHT / canvas.height
                canvas = canvas.resize((max(1, int(canvas.width * ratio)), MAX_SINGLE_IMAGE_HEIGHT), Image.LANCZOS)
            canvas.save(output_path)
        finally:
            for image in opened:
                image.close()

    def delete_temp_images(self, folder: Path) -> None:
        for file_path in folder.glob("*"):
            file_path.unlink(missing_ok=True)
        folder.rmdir()

    def set_state(self, **updates: object) -> None:
        with self.lock:
            self.state.update(updates)

    def log(self, message: str) -> None:
        with self.lock:
            logs = list(self.state["logs"])
            logs.append(message)
            self.state["logs"] = logs[-80:]


def main() -> None:
    api = ToonVaultApi()
    window = webview.create_window(
        APP_NAME,
        str(INDEX_HTML),
        js_api=api,
        width=880,
        height=640,
        min_size=(780, 560),
        text_select=True,
    )
    webview.start(private_mode=False, debug=False)


if __name__ == "__main__":
    main()
