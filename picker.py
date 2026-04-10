import json
import time
import threading
from datetime import datetime, timezone
from pathlib import Path

import flet as ft
import psycopg2
from psycopg2 import extras

# Стили (в стиле вашей WMS)
COLORS = {
    "accent": "#ff8025",
    "bg": "#0f0f0f",
    "panel": "#111111",
    "surface": "#151515",
    "muted": "#b9b9b9",
    "border": "#252525",
}

APP_DIR = Path.home() / ".bnd_picker"
CONFIG_FILE = APP_DIR / "config.json"

class PickerState:
    def __init__(self):
        APP_DIR.mkdir(parents=True, exist_ok=True)
        self.db_url = ""
        self.load()

    def load(self):
        if CONFIG_FILE.exists():
            try:
                data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
                self.db_url = data.get("db_url", "")
            except: pass

    def save(self):
        CONFIG_FILE.write_text(json.dumps({"db_url": self.db_url}, indent=2), encoding="utf-8")

class PickerApp:
    def __init__(self, page: ft.Page):
        self.page = page
        self.state = PickerState()
        self.conn = None
        self.active_picker = None
        self.idle_seconds = 300
        self.last_activity = time.time()
        
        self.timer_text = ft.Text("05:00", color=COLORS["muted"], size=12)
        
        # Поля ввода
        self.article_input = ft.TextField(label="Артикул", expand=True, bgcolor=COLORS["surface"])
        self.qty_input = ft.TextField(label="Кол-во", width=100, bgcolor=COLORS["surface"])
        self.create_table = ft.DataTable(
            columns=[ft.DataColumn(ft.Text("Артикул")), ft.DataColumn(ft.Text("Кол-во")), ft.DataColumn(ft.Text(""))],
            rows=[]
        )
        self.box_number_text = ft.Text("Номер короба: --", size=16, weight="bold")

    def connect_db(self):
        if not self.state.db_url: return False
        try:
            self.conn = psycopg2.connect(self.state.db_url)
            return True
        except: return False

    def check_idle(self):
        while True:
            if self.active_picker:
                elapsed = time.time() - self.last_activity
                remaining = max(0, self.idle_seconds - int(elapsed))
                mins, secs = divmod(remaining, 60)
                self.timer_text.value = f"{mins:02d}:{secs:02d}"
                if remaining <= 0:
                    self.logout()
                try: self.page.update()
                except: break
            time.sleep(1)

    def logout(self, e=None):
        self.active_picker = None
        if self.conn: self.conn.close()
        self.show_login()

    def show_login(self):
        self.page.controls.clear()
        code_field = ft.TextField(label="Код сборщицы", password=True, width=300, text_align=ft.TextAlign.CENTER, autofocus=True)
        error_text = ft.Text("", color=ft.Colors.RED_400)

        def do_login(e):
            if not self.connect_db():
                error_text.value = "Ошибка подключения к БД"
                self.page.update()
                return
            with self.conn.cursor(cursor_factory=extras.RealDictCursor) as cur:
                cur.execute("SELECT id, code, full_name FROM pickers WHERE code = %s", (code_field.value,))
                picker = cur.fetchone()
                if picker:
                    self.active_picker = picker
                    self.last_activity = time.time()
                    self.show_main()
                else:
                    error_text.value = "Код не найден"
                    self.page.update()

        self.page.add(
            ft.Container(
                expand=True, alignment=ft.Alignment(0, 0),
                content=ft.Column([
                    ft.Text("BnD Picker", size=32, weight="bold", color=COLORS["accent"]),
                    code_field,
                    error_text,
                    ft.FilledButton("Войти", on_click=do_login, width=300, style=ft.ButtonStyle(bgcolor=COLORS["accent"], color=ft.Colors.WHITE)),
                    ft.TextButton("Настройки", on_click=lambda _: self.show_settings())
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, tight=True)
            )
        )

    def show_settings(self):
        db_url_field = ft.TextField(label="PostgreSQL URL", value=self.state.db_url, width=500)
        def save_settings(e):
            self.state.db_url = db_url_field.value
            self.state.save()
            dlg.open = False
            self.page.update()

        dlg = ft.AlertDialog(title=ft.Text("Настройки"), content=db_url_field, actions=[ft.TextButton("ОК", on_click=save_settings)])
        self.page.overlay.append(dlg)
        dlg.open = True
        self.page.update()

    def add_to_table(self, e):
        art, qty = self.article_input.value.strip(), self.qty_input.value.strip()
        if art and qty.isdigit():
            self.create_table.rows.append(
                ft.DataRow(cells=[
                    ft.DataCell(ft.Text(art)), ft.DataCell(ft.Text(qty)),
                    ft.DataCell(ft.IconButton(ft.Icons.DELETE_OUTLINE, on_click=self.delete_row))
                ])
            )
            self.article_input.value = ""; self.qty_input.value = ""; self.article_input.focus()
            self.last_activity = time.time()
            self.page.update()

    def delete_row(self, e):
        row = e.control.parent.parent
        self.create_table.rows.remove(row)
        self.page.update()

    def save_box(self, e):
        if not self.create_table.rows: return
        with self.conn.cursor() as cur:
            cur.execute("SELECT MAX(CAST(box_code AS INTEGER)) FROM picker_boxes WHERE picker_id = %s", (self.active_picker['id'],))
            res = cur.fetchone()[0]
            box_code = str((res or 0) + 1)
            articles = [{"article": r.cells[0].content.value, "qty": int(r.cells[1].content.value)} for r in self.create_table.rows]
            cur.execute("INSERT INTO picker_boxes (picker_id, box_code, articles_json, created_at) VALUES (%s, %s, %s, NOW())",
                       (self.active_picker['id'], box_code, json.dumps(articles)))
        self.conn.commit()
        self.create_table.rows.clear()
        self.box_number_text.value = f"Номер короба: {int(box_code)+1}"
        sb = ft.SnackBar(ft.Text(f"Короб {box_code} сохранен!"), bgcolor=ft.Colors.GREEN_700)
        self.page.overlay.append(sb)
        sb.open = True
        self.page.update()

    def show_main(self):
        self.page.controls.clear()
        
        # Обновляем номер короба при входе
        with self.conn.cursor() as cur:
            cur.execute("SELECT MAX(CAST(box_code AS INTEGER)) FROM picker_boxes WHERE picker_id = %s", (self.active_picker['id'],))
            res = cur.fetchone()[0]
            self.box_number_text.value = f"Номер короба: {(res or 0) + 1}"

        header = ft.Row([
            ft.Column([ft.Text(self.active_picker['full_name'], size=18, weight="bold"), ft.Text(f"Код: {self.active_picker['code']}", size=12, color=COLORS["muted"])]),
            ft.Row([self.timer_text, ft.IconButton(ft.Icons.LOGOUT, on_click=self.logout)])
        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN)

        # Контент для первой вкладки
        tab_create_content = ft.Container(
            padding=20,
            content=ft.Column([
                self.box_number_text,
                ft.Row([self.article_input, self.qty_input, ft.FloatingActionButton(icon=ft.Icons.ADD, on_click=self.add_to_table, bgcolor=COLORS["accent"])]),
                ft.Container(content=ft.Column([self.create_table], scroll=ft.ScrollMode.ADAPTIVE), bgcolor=COLORS["surface"], border_radius=10, padding=10, expand=True),
                ft.FilledButton("Сохранить короб", on_click=self.save_box, width=float("inf"), height=50, style=ft.ButtonStyle(bgcolor=COLORS["accent"], color=ft.Colors.WHITE))
            ], expand=True)
        )

        # Структура Tabs для 0.84.0
        # 1. Список заголовков
        tab_bar = ft.TabBar(
            tabs=[ft.Tab(label="Создать короб"), ft.Tab(label="Статистика")],
            indicator_color=COLORS["accent"],
            label_color=ft.Colors.WHITE,
            unselected_label_color=COLORS["muted"],
        )
        
        # 2. Список содержимого
        tab_view = ft.TabBarView(
            expand=True,
            controls=[
                tab_create_content,
                ft.Container(content=ft.Text("Модуль статистики в разработке"), padding=20)
            ]
        )

        # 3. Объединение в Tabs
        tabs_root = ft.Tabs(
            length=2,
            selected_index=0,
            expand=True,
            content=ft.Column([tab_bar, tab_view])
        )

        self.page.add(ft.Container(expand=True, bgcolor=COLORS["bg"], content=ft.Column([header, ft.Divider(color=COLORS["border"]), tabs_root])))
        threading.Thread(target=self.check_idle, daemon=True).start()

def main(page: ft.Page):
    page.title = "BnD Picker"; page.theme_mode = ft.ThemeMode.DARK; page.bgcolor = COLORS["bg"]
    PickerApp(page).show_login()

if __name__ == "__main__":
    ft.run(main)