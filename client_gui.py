import flet as ft
import socket
import threading
import sys
import time

# CONFIGURAZIONE
SERVER_IP = '127.0.0.1'
SERVER_PORT = 4000

class ChatClient:
    def __init__(self, page: ft.Page):
        self.page = page
        self.page.title = "Python Flet Chat"
        self.page.theme_mode = ft.ThemeMode.DARK
        self.page.window_width = 400
        self.page.window_height = 650
        self.sock = None
        self.nickname = ""
        self.running = False 

        # --- UI LOGIN ---
        self.txt_nickname = ft.TextField(
            label="Nickname", width=200, autofocus=True, on_submit=self.connetti_click
        )
        self.btn_login = ft.ElevatedButton("Entra", width=200, on_click=self.connetti_click)
        self.error_text = ft.Text("", color=ft.Colors.RED)

        self.login_container = ft.Container(
            content=ft.Column([
                ft.Icon(ft.Icons.CHAT, size=60, color=ft.Colors.BLUE),
                ft.Text("Benvenuto", size=24, weight="bold"),
                self.txt_nickname,
                self.btn_login,
                self.error_text
            ], alignment="center", horizontal_alignment="center", spacing=20),
            alignment=ft.alignment.center, expand=True
        )

        self.chat_list = ft.ListView(expand=True, spacing=10, auto_scroll=True, padding=10)
        self.txt_message = ft.TextField(
            hint_text="Messaggio... (usa JOIN <nome> per cambiare stanza)",
            autofocus=True, shift_enter=True, min_lines=1, max_lines=5, expand=True,
            on_submit=self.send_message
        )
        self.btn_send = ft.IconButton(ft.Icons.SEND_ROUNDED, icon_color=ft.Colors.BLUE, on_click=self.send_message)

        self.chat_container = ft.Column([
            ft.Container(
                content=self.chat_list,
                border=ft.border.all(1, ft.Colors.GREY_300),
                border_radius=10, expand=True
            ),
            ft.Row([self.txt_message, self.btn_send])
        ], expand=True, visible=False)

        self.page.add(self.login_container, self.chat_container)

    def connetti_click(self, e):
        if not self.txt_nickname.value:
            self.error_text.value = "Inserisci un nickname!"
            self.page.update()
            return

        self.nickname = self.txt_nickname.value
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.connect((SERVER_IP, SERVER_PORT))
            
            self.running = True
            
            # Switch GUI
            self.login_container.visible = False
            self.chat_container.visible = True
            self.page.title = f"Chat: {self.nickname}"
            self.page.update()

            # Avvia ricezione
            threading.Thread(target=self.receive_loop, daemon=True).start()

            # 1. Invia Nickname
            self.sock.sendall(self.nickname.encode('utf-8'))
            time.sleep(0.1) # Breve pausa tecnica
            # 2. Invia AUTO-JOIN per non restare nel limbo
            self.sock.sendall("JOIN generale".encode('utf-8'))

        except Exception as err:
            self.error_text.value = f"Errore: {err}"
            self.page.update()

    def receive_loop(self):
        """Riceve i dati gestendo il buffer TCP correttamente"""
        buffer = ""
        while self.running:
            try:
                data = self.sock.recv(1024).decode('utf-8')
                if not data:
                    self.add_message_to_ui("⚠️ Server disconnesso.")
                    self.running = False
                    break
                
                buffer += data
                
                while "\n" in buffer:
                    msg, buffer = buffer.split("\n", 1)
                    if msg.strip():
                        self.add_message_to_ui(msg)
            except:
                break

    def add_message_to_ui(self, msg):
        is_me = msg.startswith(f"{self.nickname}:") or msg.startswith(f"[{self.nickname}]")
        is_server = "SERVER:" in msg or "Benvenuto" in msg or "⚠️" in msg
        
        align = ft.MainAxisAlignment.END if is_me else ft.MainAxisAlignment.START

        if is_me:
            bg = ft.Colors.BLUE_900 
        elif is_server:uro
            bg = ft.Colors.ORANGE_900
            align = ft.MainAxisAlignment.CENTER
        else:
            bg = ft.Colors.GREY_800

        bubble = ft.Row([
            ft.Container(
                content=ft.Text(msg), 
                padding=10, 
                border_radius=10, 
                bgcolor=bg,
            )
        ], alignment=align)

        self.chat_list.controls.append(bubble)
        self.page.update()

    def send_message(self, e):
        text = self.txt_message.value
        if not text: return

        try:
            self.sock.sendall(text.encode('utf-8'))
            if text.upper() != "EXIT":
                self.add_message_to_ui(f"{self.nickname}: {text}")
            self.txt_message.value = ""
            self.txt_message.focus()
            self.page.update()
            if text.upper() == "EXIT":
                self.running = False
                self.sock.close()
                self.page.window_close()
        except Exception as e:
            self.add_message_to_ui(f"⚠️ Errore invio: {e}")
            
def main(page: ft.Page):
    client = ChatClient(page)

if __name__ == "__main__":

    ft.app(target=main)
