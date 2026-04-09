from __future__ import annotations

import json
from datetime import datetime, timezone
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import flet as ft

APP_NAME = "BnDWMS"
STORAGE_DIR = Path.home() / ".bndwms"
STATE_PATH = STORAGE_DIR / "state.json"

COLORS = {
    "accent": "#ff8025",
    "bg": "#0f0f0f",
    "panel": "#111111",
    "surface": "#151515",
    "muted": "#b9b9b9",
    "border": "#252525",
}


def border_all(width: float, color: str) -> ft.Border:
    border_type = getattr(ft, "Border", None)
    if border_type is not None and hasattr(border_type, "all"):
        return border_type.all(width=width, color=color)
    return ft.border.all(width, color)


@dataclass
class WMSState:
    db_url: str = ""
    users: dict[str, dict[str, str]] = field(
        default_factory=lambda: {
            "Admin": {"pin": "Zhabus", "role": "Администратор"},
            "Оператор": {"pin": "123456", "role": "Оператор"},
        }
    )
    warehouses: list[str] = field(default_factory=lambda: ["Основной"])
    plugins: dict[str, bool] = field(
        default_factory=lambda: {
            "label_printer": True,
            "warehouse_import": True,
            "warehouse_export": True,
            "audit_log": False,
        }
    )
    label_printer: dict[str, str | bool] = field(
        default_factory=lambda: {
            "enabled": True,
            "model": "Zebra ZD421",
            "connection": "USB",
            "dpi": "300",
            "template": "58x40",
        }
    )
    import_export: dict[str, str | bool] = field(
        default_factory=lambda: {
            "auto_backup": True,
            "import_path": str(STORAGE_DIR / "stock_import.json"),
            "export_path": str(STORAGE_DIR / "stock_export.json"),
            "last_import": "",
            "last_export": "",
        }
    )
    stock_rows: list[dict[str, str]] = field(
        default_factory=lambda: [
            {"article": "A-100", "name": "Тестовый товар", "qty": "25"},
            {"article": "A-220", "name": "Кабель UTP", "qty": "13"},
            {"article": "B-007", "name": "Сканер", "qty": "4"},
        ]
    )

    @classmethod
    def load(cls) -> "WMSState":
        STORAGE_DIR.mkdir(parents=True, exist_ok=True)
        if not STATE_PATH.exists():
            state = cls()
            state.save()
            return state

        try:
            raw: dict[str, Any] = json.loads(STATE_PATH.read_text(encoding="utf-8"))
            state = cls()
            state.db_url = str(raw.get("db_url", ""))
            state.users = state._parse_users(raw.get("users", state.users))
            state.warehouses = list(raw.get("warehouses", state.warehouses))
            state.plugins = state._parse_plugins(raw.get("plugins", state.plugins))
            state.label_printer = state._parse_printer(raw.get("label_printer", state.label_printer))
            state.import_export = state._parse_import_export(raw.get("import_export", state.import_export))

            rows = raw.get("stock_rows", state.stock_rows)
            if isinstance(rows, list):
                parsed_rows = [
                    {
                        "article": str(item.get("article", "")),
                        "name": str(item.get("name", "")),
                        "qty": str(item.get("qty", "0")),
                    }
                    for item in rows
                    if isinstance(item, dict)
                ]
                if parsed_rows:
                    state.stock_rows = parsed_rows

            return state
        except Exception:
            fallback = cls()
            fallback.save()
            return fallback

    def save(self) -> None:
        payload = {
            "db_url": self.db_url,
            "users": self.users,
            "warehouses": self.warehouses,
            "plugins": self.plugins,
            "label_printer": self.label_printer,
            "import_export": self.import_export,
            "stock_rows": self.stock_rows,
        }
        STATE_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def _parse_users(raw_users: Any) -> dict[str, dict[str, str]]:
        parsed: dict[str, dict[str, str]] = {}
        if isinstance(raw_users, dict):
            for user_name, user_payload in raw_users.items():
                if not isinstance(user_name, str):
                    continue
                if isinstance(user_payload, dict):
                    pin = str(user_payload.get("pin", "")).strip()
                    role = str(user_payload.get("role", "Оператор")).strip() or "Оператор"
                else:
                    pin = str(user_payload).strip()
                    role = "Администратор" if user_name == "Admin" else "Оператор"
                if pin:
                    parsed[user_name] = {"pin": pin, "role": role}
        if "Admin" not in parsed:
            parsed["Admin"] = {"pin": "Zhabus", "role": "Администратор"}
        return parsed

    @staticmethod
    def _parse_plugins(raw_plugins: Any) -> dict[str, bool]:
        defaults = WMSState().plugins
        if not isinstance(raw_plugins, dict):
            return defaults
        parsed = defaults.copy()
        for key in parsed:
            parsed[key] = bool(raw_plugins.get(key, parsed[key]))
        return parsed

    @staticmethod
    def _parse_printer(raw_printer: Any) -> dict[str, str | bool]:
        defaults = WMSState().label_printer
        if not isinstance(raw_printer, dict):
            return defaults
        parsed = defaults.copy()
        for key, default_value in defaults.items():
            value = raw_printer.get(key, default_value)
            parsed[key] = bool(value) if isinstance(default_value, bool) else str(value)
        return parsed

    @staticmethod
    def _parse_import_export(raw_state: Any) -> dict[str, str | bool]:
        defaults = WMSState().import_export
        if not isinstance(raw_state, dict):
            return defaults
        parsed = defaults.copy()
        for key, default_value in defaults.items():
            value = raw_state.get(key, default_value)
            parsed[key] = bool(value) if isinstance(default_value, bool) else str(value)
        return parsed


class BndWmsApplication:
    def __init__(self, page: ft.Page) -> None:
        self.page = page
        self.state = WMSState.load()
        self.active_user = ""
        self.status_line = ft.Text("Готово", color=COLORS["muted"], size=12)

        self._tab_titles = ["Приёмка", "Перемещение", "Списание", "Инвентаризация", "Остатки", "Настройки"]
        self.tabs_root = self._build_tabs()
        self.settings_users_column: ft.Column | None = None

    def _build_tabs(self) -> ft.Tabs:
        return ft.Tabs(
            tabs=[
                ft.Tab(text="Приёмка", content=self._operation_tab_body("Приёмка")),
                ft.Tab(text="Перемещение", content=self._operation_tab_body("Перемещение")),
                ft.Tab(text="Списание", content=self._operation_tab_body("Списание")),
                ft.Tab(text="Инвентаризация", content=self._operation_tab_body("Инвентаризация")),
                ft.Tab(text="Остатки", content=self._stock_tab_body()),
                ft.Tab(text="Настройки", content=self._settings_tab_body()),
            ],
            selected_index=0,
            scrollable=False,
            animation_duration=180,
            divider_color=COLORS["border"],
            indicator_color=COLORS["accent"],
            label_color=ft.Colors.WHITE,
            unselected_label_color=COLORS["muted"],
            expand=True,
        )

    def start(self) -> None:
        self.page.title = f"{APP_NAME} — Flet"
        self.page.bgcolor = COLORS["bg"]
        self.page.theme_mode = ft.ThemeMode.DARK
        self.page.theme = ft.Theme(color_scheme_seed=COLORS["accent"])
        self.page.padding = 18

        # Window size matters only for desktop/desktop-like runtimes.
        try:
            self.page.window.min_width = 980
            self.page.window.min_height = 640
        except Exception:
            pass

        self.page.on_keyboard_event = self._on_hotkey

        self.page.controls.clear()
        self.page.add(self._login_screen())
        self.page.update()

    def _login_screen(self) -> ft.Control:
        fio = ft.TextField(label="ФИО", autofocus=True, bgcolor=COLORS["surface"], border_radius=10)
        pin = ft.TextField(
            label="PIN",
            password=True,
            can_reveal_password=True,
            bgcolor=COLORS["surface"],
            border_radius=10,
        )
        warning = ft.Text("", color=ft.Colors.RED_300)

        def sign_in(_: ft.ControlEvent) -> None:
            username = (fio.value or "").strip()
            password = (pin.value or "").strip()

            if not username or not password:
                warning.value = "Введите ФИО и PIN"
                self.page.update()
                return

            user = self.state.users.get(username)
            if not user or user.get("pin") != password:
                warning.value = "Неверный логин или PIN"
                self.page.update()
                return

            self.active_user = username
            self.tabs_root = self._build_tabs()
            self.page.controls.clear()
            self.page.add(self._main_screen())
            self._set_status(f"Вход выполнен: {username}")

        return ft.Container(
            expand=True,
            alignment=ft.Alignment.CENTER,
            content=ft.Container(
                width=390,
                padding=24,
                bgcolor=COLORS["panel"],
                border_radius=16,
                border=border_all(1, COLORS["border"]),
                content=ft.Column(
                    tight=True,
                    spacing=12,
                    controls=[
                        ft.Text("Вход в BnDWMS", size=22, weight=ft.FontWeight.W_600),
                        ft.Text("Новый интерфейс на Flet", size=12, color=COLORS["muted"]),
                        fio,
                        pin,
                        warning,
                        ft.FilledButton(
                            "Войти",
                            style=ft.ButtonStyle(bgcolor=COLORS["accent"], color=ft.Colors.WHITE),
                            on_click=sign_in,
                        ),
                    ],
                ),
            ),
        )

    def _main_screen(self) -> ft.Control:
        return ft.Column(
            expand=True,
            spacing=0,
            controls=[
                ft.Row(
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    controls=[
                        ft.Column(
                            spacing=2,
                            controls=[
                                ft.Text(APP_NAME, size=24, weight=ft.FontWeight.W_700),
                                ft.Text(f"Пользователь: {self.active_user}", color=COLORS["muted"], size=12),
                            ],
                        ),
                        ft.Text("F1–F6 — быстрые вкладки", color=COLORS["muted"], size=11),
                    ],
                ),
                ft.Container(height=8),
                ft.Container(
                    expand=True,
                    padding=12,
                    bgcolor=COLORS["panel"],
                    border_radius=14,
                    content=self.tabs_root,
                ),
                ft.Container(
                    padding=10,
                    bgcolor="#121212",
                    border_radius=10,
                    content=ft.Row(
                        controls=[
                            ft.Icon(ft.Icons.INFO_OUTLINE, size=16, color=COLORS["muted"]),
                            self.status_line,
                        ]
                    ),
                ),
            ],
        )

    def _operation_tab_body(self, title: str) -> ft.Control:
        article = ft.TextField(label="Артикул", bgcolor=COLORS["surface"])
        qty = ft.TextField(label="Количество", bgcolor=COLORS["surface"])
        warehouse = ft.Dropdown(
            label="Склад",
            bgcolor=COLORS["surface"],
            value=self.state.warehouses[0] if self.state.warehouses else None,
            options=[ft.dropdown.Option(item) for item in self.state.warehouses],
        )

        def post_operation(_: ft.ControlEvent) -> None:
            self._set_status(
                f"{title}: артикул {article.value or '-'} / количество {qty.value or '-'} / склад {warehouse.value or '-'}"
            )

        return ft.Container(
            padding=16,
            content=ft.Column(
                spacing=12,
                controls=[
                    ft.Text(title, size=20, weight=ft.FontWeight.W_600),
                    ft.Text("Операция складского учёта.", color=COLORS["muted"]),
                    article,
                    qty,
                    warehouse,
                    ft.FilledButton(
                        "Провести",
                        style=ft.ButtonStyle(bgcolor=COLORS["accent"], color=ft.Colors.WHITE),
                        on_click=post_operation,
                    ),
                ],
            ),
        )

    def _stock_tab_body(self) -> ft.Control:
        table = ft.DataTable(
            columns=[
                ft.DataColumn(ft.Text("Артикул")),
                ft.DataColumn(ft.Text("Название")),
                ft.DataColumn(ft.Text("Кол-во")),
            ],
            rows=[
                ft.DataRow(
                    cells=[
                        ft.DataCell(ft.Text(row["article"])),
                        ft.DataCell(ft.Text(row["name"])),
                        ft.DataCell(ft.Text(row["qty"])),
                    ]
                )
                for row in self.state.stock_rows
            ],
        )

        return ft.Container(
            padding=16,
            content=ft.Column(
                spacing=12,
                controls=[
                    ft.Text("Остатки", size=20, weight=ft.FontWeight.W_600),
                    ft.Text("Снимок складских остатков из локального состояния.", color=COLORS["muted"]),
                    ft.Container(padding=12, bgcolor=COLORS["surface"], border_radius=12, content=table),
                ],
            ),
        )

    def _settings_tab_body(self) -> ft.Control:
        db_field = ft.TextField(label="PostgreSQL URL", value=self.state.db_url, bgcolor=COLORS["surface"])

        def persist(_: ft.ControlEvent) -> None:
            self.state.db_url = db_field.value or ""
            self.state.save()
            self._set_status("Настройки сохранены")

        basic_settings = ft.Container(
            padding=16,
            bgcolor=COLORS["surface"],
            border_radius=12,
            content=ft.Column(
                spacing=12,
                controls=[
                    ft.Text("Базовые настройки", size=16, weight=ft.FontWeight.W_600),
                    db_field,
                    ft.FilledButton(
                        "Сохранить",
                        style=ft.ButtonStyle(bgcolor=COLORS["accent"], color=ft.Colors.WHITE),
                        on_click=persist,
                    ),
                ],
            ),
        )

        if self.active_user != "Admin":
            return ft.Container(
                padding=16,
                content=ft.Column(
                    spacing=12,
                    controls=[
                        ft.Text("Настройки", size=20, weight=ft.FontWeight.W_600),
                        basic_settings,
                        ft.Container(
                            padding=12,
                            bgcolor=COLORS["surface"],
                            border_radius=12,
                            content=ft.Text(
                                "Административные функции доступны только учётной записи Admin.",
                                color=COLORS["muted"],
                            ),
                        ),
                    ],
                ),
            )

        return self._admin_settings_tab(basic_settings)

    def _admin_settings_tab(self, basic_settings: ft.Control) -> ft.Control:
        user_name = ft.TextField(label="ФИО пользователя", bgcolor=COLORS["surface"])
        user_pin = ft.TextField(label="PIN", bgcolor=COLORS["surface"], can_reveal_password=True, password=True)
        user_role = ft.Dropdown(
            label="Роль",
            bgcolor=COLORS["surface"],
            value="Оператор",
            options=[ft.dropdown.Option("Оператор"), ft.dropdown.Option("Администратор")],
        )
        self.settings_users_column = ft.Column(spacing=6)

        def refresh_users() -> None:
            assert self.settings_users_column is not None
            rows: list[ft.Control] = []
            for name, user in sorted(self.state.users.items()):
                role = user.get("role", "Оператор")

                def remove_user(_: ft.ControlEvent, username: str = name) -> None:
                    if username == "Admin":
                        self._set_status("Пользователь Admin не может быть удалён")
                        return
                    self.state.users.pop(username, None)
                    self.state.save()
                    refresh_users()
                    self._set_status(f"Пользователь {username} удалён")

                rows.append(
                    ft.Container(
                        padding=10,
                        border_radius=8,
                        bgcolor=COLORS["panel"],
                        content=ft.Row(
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                            controls=[
                                ft.Column(
                                    spacing=2,
                                    controls=[
                                        ft.Text(name, weight=ft.FontWeight.W_600),
                                        ft.Text(role, color=COLORS["muted"], size=12),
                                    ],
                                ),
                                ft.OutlinedButton(
                                    "Удалить",
                                    disabled=name == "Admin",
                                    on_click=remove_user,
                                ),
                            ],
                        ),
                    )
                )
            self.settings_users_column.controls = rows
            self.page.update()

        def add_or_update_user(_: ft.ControlEvent) -> None:
            username = (user_name.value or "").strip()
            pin = (user_pin.value or "").strip()
            role = (user_role.value or "Оператор").strip()
            if not username or not pin:
                self._set_status("Для пользователя требуется ФИО и PIN")
                return

            self.state.users[username] = {"pin": pin, "role": role}
            self.state.save()
            refresh_users()
            user_name.value = ""
            user_pin.value = ""
            user_role.value = "Оператор"
            self._set_status(f"Пользователь {username} сохранён")
            self.page.update()

        plugin_labels = {
            "label_printer": "Плагин печати этикеток",
            "warehouse_import": "Плагин импорта склада",
            "warehouse_export": "Плагин экспорта склада",
            "audit_log": "Плагин аудита действий",
        }
        plugin_switches = []
        for plugin_key, plugin_title in plugin_labels.items():
            switch = ft.Switch(label=plugin_title, value=self.state.plugins.get(plugin_key, False))

            def toggle_plugin(event: ft.ControlEvent, key: str = plugin_key) -> None:
                self.state.plugins[key] = bool(event.control.value)
                self.state.save()
                self._set_status(f"{plugin_labels[key]}: {'включён' if event.control.value else 'отключён'}")

            switch.on_change = toggle_plugin
            plugin_switches.append(switch)

        printer_enabled = ft.Switch(label="Использовать принтер этикеток", value=bool(self.state.label_printer["enabled"]))
        printer_model = ft.TextField(
            label="Модель принтера",
            value=str(self.state.label_printer["model"]),
            bgcolor=COLORS["surface"],
        )
        printer_connection = ft.Dropdown(
            label="Подключение",
            bgcolor=COLORS["surface"],
            value=str(self.state.label_printer["connection"]),
            options=[ft.dropdown.Option("USB"), ft.dropdown.Option("TCP/IP"), ft.dropdown.Option("Bluetooth")],
        )
        printer_dpi = ft.Dropdown(
            label="Разрешение DPI",
            bgcolor=COLORS["surface"],
            value=str(self.state.label_printer["dpi"]),
            options=[ft.dropdown.Option("203"), ft.dropdown.Option("300"), ft.dropdown.Option("600")],
        )
        printer_template = ft.Dropdown(
            label="Шаблон этикетки",
            bgcolor=COLORS["surface"],
            value=str(self.state.label_printer["template"]),
            options=[ft.dropdown.Option("58x40"), ft.dropdown.Option("58x30"), ft.dropdown.Option("100x50")],
        )

        def save_printer(_: ft.ControlEvent) -> None:
            self.state.label_printer = {
                "enabled": bool(printer_enabled.value),
                "model": printer_model.value or "",
                "connection": printer_connection.value or "USB",
                "dpi": printer_dpi.value or "300",
                "template": printer_template.value or "58x40",
            }
            self.state.save()
            self._set_status("Параметры принтера этикеток сохранены")

        import_path = ft.TextField(
            label="Файл импорта (JSON)",
            value=str(self.state.import_export["import_path"]),
            bgcolor=COLORS["surface"],
        )
        export_path = ft.TextField(
            label="Файл экспорта (JSON)",
            value=str(self.state.import_export["export_path"]),
            bgcolor=COLORS["surface"],
        )
        auto_backup = ft.Switch(
            label="Авто-резервная копия перед импортом",
            value=bool(self.state.import_export["auto_backup"]),
        )
        import_info = ft.Text(
            f"Последний импорт: {self.state.import_export.get('last_import') or 'не выполнялся'}",
            color=COLORS["muted"],
            size=12,
        )
        export_info = ft.Text(
            f"Последний экспорт: {self.state.import_export.get('last_export') or 'не выполнялся'}",
            color=COLORS["muted"],
            size=12,
        )

        def persist_import_export() -> None:
            self.state.import_export["import_path"] = import_path.value or ""
            self.state.import_export["export_path"] = export_path.value or ""
            self.state.import_export["auto_backup"] = bool(auto_backup.value)
            self.state.save()

        def export_stock(_: ft.ControlEvent) -> None:
            persist_import_export()
            target = Path(str(self.state.import_export["export_path"]))
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(self.state.stock_rows, ensure_ascii=False, indent=2), encoding="utf-8")
            self.state.import_export["last_export"] = datetime.now(timezone.utc).isoformat()
            self.state.save()
            export_info.value = f"Последний экспорт: {self.state.import_export['last_export']}"
            self._set_status(f"Остатки экспортированы: {target}")

        def import_stock(_: ft.ControlEvent) -> None:
            persist_import_export()
            source = Path(str(self.state.import_export["import_path"]))
            if not source.exists():
                self._set_status(f"Файл импорта не найден: {source}")
                return
            payload = json.loads(source.read_text(encoding="utf-8"))
            if not isinstance(payload, list):
                self._set_status("Ошибка импорта: ожидается список объектов")
                return

            parsed_rows = [
                {
                    "article": str(item.get("article", "")),
                    "name": str(item.get("name", "")),
                    "qty": str(item.get("qty", "0")),
                }
                for item in payload
                if isinstance(item, dict)
            ]
            if not parsed_rows:
                self._set_status("Ошибка импорта: список пуст или повреждён")
                return

            if bool(self.state.import_export["auto_backup"]):
                backup_path = Path(str(self.state.import_export["export_path"])).with_suffix(".backup.json")
                backup_path.parent.mkdir(parents=True, exist_ok=True)
                backup_path.write_text(json.dumps(self.state.stock_rows, ensure_ascii=False, indent=2), encoding="utf-8")

            self.state.stock_rows = parsed_rows
            self.state.import_export["last_import"] = datetime.now(timezone.utc).isoformat()
            self.state.save()
            import_info.value = f"Последний импорт: {self.state.import_export['last_import']}"
            self._set_status(f"Импортировано позиций: {len(parsed_rows)}")

        refresh_users()

        return ft.Container(
            padding=16,
            content=ft.Column(
                spacing=12,
                controls=[
                    ft.Text("Настройки", size=20, weight=ft.FontWeight.W_600),
                    basic_settings,
                    ft.Container(
                        padding=16,
                        bgcolor=COLORS["surface"],
                        border_radius=12,
                        content=ft.Column(
                            spacing=10,
                            controls=[
                                ft.Text("Управление пользователями", size=16, weight=ft.FontWeight.W_600),
                                ft.Text("Только для учётной записи Admin.", color=COLORS["muted"], size=12),
                                user_name,
                                user_pin,
                                user_role,
                                ft.FilledButton(
                                    "Добавить / обновить пользователя",
                                    style=ft.ButtonStyle(bgcolor=COLORS["accent"], color=ft.Colors.WHITE),
                                    on_click=add_or_update_user,
                                ),
                                self.settings_users_column,
                            ],
                        ),
                    ),
                    ft.Container(
                        padding=16,
                        bgcolor=COLORS["surface"],
                        border_radius=12,
                        content=ft.Column(
                            spacing=8,
                            controls=[
                                ft.Text("Подключение плагинов", size=16, weight=ft.FontWeight.W_600),
                                *plugin_switches,
                            ],
                        ),
                    ),
                    ft.Container(
                        padding=16,
                        bgcolor=COLORS["surface"],
                        border_radius=12,
                        content=ft.Column(
                            spacing=10,
                            controls=[
                                ft.Text("Принтер этикеток", size=16, weight=ft.FontWeight.W_600),
                                printer_enabled,
                                printer_model,
                                printer_connection,
                                printer_dpi,
                                printer_template,
                                ft.FilledButton(
                                    "Сохранить параметры принтера",
                                    style=ft.ButtonStyle(bgcolor=COLORS["accent"], color=ft.Colors.WHITE),
                                    on_click=save_printer,
                                ),
                            ],
                        ),
                    ),
                    ft.Container(
                        padding=16,
                        bgcolor=COLORS["surface"],
                        border_radius=12,
                        content=ft.Column(
                            spacing=10,
                            controls=[
                                ft.Text("Импорт / экспорт склада", size=16, weight=ft.FontWeight.W_600),
                                import_path,
                                export_path,
                                auto_backup,
                                ft.Row(
                                    controls=[
                                        ft.FilledButton(
                                            "Импортировать остатки",
                                            style=ft.ButtonStyle(bgcolor=COLORS["accent"], color=ft.Colors.WHITE),
                                            on_click=import_stock,
                                        ),
                                        ft.OutlinedButton("Экспортировать остатки", on_click=export_stock),
                                    ],
                                ),
                                import_info,
                                export_info,
                            ],
                        ),
                    ),
                ],
            ),
        )

    def _set_status(self, message: str) -> None:
        self.status_line.value = message
        self.page.update()

    def _on_hotkey(self, event: ft.KeyboardEvent) -> None:
        mapping = {"f1": 0, "f2": 1, "f3": 2, "f4": 3, "f5": 4, "f6": 5}
        target = mapping.get((event.key or "").lower())
        if target is None:
            return

        self.tabs_root.selected_index = target
        self.page.update()


def main(page: ft.Page) -> None:
    BndWmsApplication(page).start()


if __name__ == "__main__":
    if hasattr(ft, "run"):
        ft.run(main)
    else:
        ft.app(target=main)
