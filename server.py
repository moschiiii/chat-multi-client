import socket
import threading

# STRUTTURE DATI
# clients: socket -> {"nickname": str, "channel": str o None}
clients = {}
# channels: nome -> {"members": [socket], "admin": socket, "banned": set()}
channels = {}

lock = threading.Lock()

# ----------------------------------------------------------
# FUNZIONI DI UTILITÀ
# ----------------------------------------------------------
def send(sock, msg):
    """Invia messaggio gestendo eventuali errori di socket."""
    try: sock.sendall((msg + "\n").encode("utf-8"))
    except: pass

def broadcast(channel, msg, exclude=None):
    """Invia a tutti i membri di un canale (eccetto 'exclude')."""
    if channel in channels:
        for s in channels[channel]["members"]:
            if s != exclude: send(s, msg)

def find_socket(nickname):
    """Trova il socket di un utente dal nickname (case insensitive)."""
    return next((s for s, i in clients.items() if i["nickname"].lower() == nickname.lower()), None)

# ----------------------------------------------------------
# LOGICA CANALI
# ----------------------------------------------------------
def leave_channel(sock):
    """Gestisce l'uscita di un utente dal canale corrente."""
    if sock not in clients: return # Sicurezza

    nick = clients[sock]["nickname"]
    chan_name = clients[sock]["channel"]
    
    if not chan_name or chan_name not in channels: return

    info = channels[chan_name]
    if sock in info["members"]:
        info["members"].remove(sock)
        # Avvisa gli altri che è uscito (o è stato cacciato)
        broadcast(chan_name, f"SERVER: {nick} ha lasciato il canale.")

        # Gestione Admin: se l'admin esce, passa il ruolo o cancella la stanza
        if info["admin"] == sock:
            if info["members"]:
                info["admin"] = info["members"][0]
                send(info["admin"], "SERVER: Ora sei l'amministratore del canale.")
            else:
                del channels[chan_name] # Canale vuoto, elimina

    clients[sock]["channel"] = None

def join_channel(sock, new_channel):
    """Gestisce l'ingresso in un canale con controllo BAN."""
    nick = clients[sock]["nickname"]
    
    # --- MODIFICA 1: Controllo BAN all'ingresso ---
    if new_channel in channels:
        # Controlliamo se il nickname è nella lista bannati
        if nick in channels[new_channel]["banned"]:
            send(sock, f"SERVER: Accesso negato. Sei BANNATO da '{new_channel}'.")
            return 
    # ----------------------------------------------

    # 1. Esce dal vecchio canale (se presente)
    leave_channel(sock)

    # 2. Crea il canale se non esiste
    if new_channel not in channels:
        channels[new_channel] = {"members": [], "admin": sock, "banned": set()}
        send(sock, f"SERVER: Canale '{new_channel}' creato. Sei ADMIN.")

    # 3. Entra nel nuovo canale
    channels[new_channel]["members"].append(sock)
    clients[sock]["channel"] = new_channel
    
    send(sock, f"SERVER: Entrato nel canale '{new_channel}'.")
    broadcast(new_channel, f"{nick} è entrato.", exclude=sock)

# ----------------------------------------------------------
# GESTIONE CLIENT (THREAD)
# ----------------------------------------------------------
def handle_client(sock, addr):
    print(f"[+] Connessione da {addr}")
    
    # --- FASE 1: Scelta Nickname ---
    nick = ""
    while True:
        send(sock, "Inserisci Nickname:")
        try: nick = sock.recv(1024).decode().strip()
        except: break
        
        if not nick or " " in nick: continue
        
        with lock:
            if any(c["nickname"].lower() == nick.lower() for c in clients.values()):
                send(sock, "Nickname in uso.")
                continue
            clients[sock] = {"nickname": nick, "channel": None}
            break
            
    send(sock, f"Benvenuto {nick}! Comandi: JOIN <canale>, Lista comandi: HELP, Per uscire: EXIT")

    # --- FASE 2: Loop Comandi ---
    while True:
        try:
            data = sock.recv(1024)
            if not data: break
            msg = data.decode().strip()
            if not msg: continue

            nick = clients[sock]["nickname"]
            chan = clients[sock]["channel"]
            upper_msg = msg.upper()

            # --- COMANDI UTENTE ---
            if upper_msg == "EXIT": break
            
            elif upper_msg == "HELP":
                send(sock, "Comandi generali: JOIN <canale>, Lista canali: 'CHANNELS' , Utenti collegati: 'USERS', Canale corrente: 'MYCHANNEL', BAN <n>, UNBAN <n>")
            
            elif upper_msg == "CHANNELS":
                send(sock, "Lista canali aperti: " + ", ".join(channels.keys()) if channels else "Nessun canale.")
            
            elif upper_msg == "USERS":
                send(sock, "Utenti online: " + ", ".join(c["nickname"] for c in clients.values()))
            
            elif upper_msg == "MYCHANNEL":
                send(sock, f"Canale attuale: {chan}" if chan else "Nessun canale.")

            elif msg.startswith("/w "):
                try:
                    _, target_nick, text = msg.split(" ", 2)
                    target_sock = find_socket(target_nick)
                    if target_sock:
                        send(target_sock, f"[Privato] {nick}: {text}")
                        send(sock, f"[A {target_nick}]: {text}")
                    else: send(sock, "Utente non trovato.")
                except: send(sock, "Uso: /w <nick> <msg>")

            elif upper_msg.startswith("JOIN "):
                try:
                    new_c = msg.split(" ", 1)[1].strip()
                    if " " in new_c: send(sock, "No spazi nel nome canale.")
                    else:
                        with lock: join_channel(sock, new_c)
                except: send(sock, "Uso: JOIN <nome_canale>")

            # --- COMANDI ADMIN (BAN/UNBAN) ---
            elif upper_msg.startswith(("BAN ", "UNBAN ", "BANLIST")):
                if not chan: 
                    send(sock, "Entra prima in un canale.")
                    continue
                
                if upper_msg == "BANLIST":
                    banned_list = channels[chan]["banned"]
                    send(sock, "Bannati: " + (", ".join(banned_list) if banned_list else "Nessuno"))
                    continue

                if channels[chan]["admin"] != sock:
                    send(sock, "Serve essere ADMIN.")
                    continue

                try: target_name = msg.split(" ", 1)[1].strip()
                except: continue

                # --- MODIFICA 2: Logica BAN Corretta ---
                if upper_msg.startswith("BAN "):
                    if target_name.lower() == nick.lower(): 
                        send(sock, "Non puoi bannarti da solo.")
                    else:
                        target_sock = find_socket(target_name)
                        # Verifica se esiste e se è nel TUO canale
                        if target_sock and target_sock in channels[chan]["members"]:
                            # 1. Aggiungi alla blacklist
                            channels[chan]["banned"].add(target_name)
                            # 2. Avvisa tutti
                            broadcast(chan, f"⚠️ {target_name} è stato BANNATO da {nick}.")
                            # 3. Notifica vittima
                            send(target_sock, f"SEI STATO BANNATO DAL CANALE '{chan}'.")
                            # 4. Buttalo fuori fisicamente
                            leave_channel(target_sock)
                        else: 
                            send(sock, "Utente non trovato nel canale.")
                # ---------------------------------------
                
                elif upper_msg.startswith("UNBAN "):
                    if target_name in channels[chan]["banned"]:
                        channels[chan]["banned"].remove(target_name)
                        broadcast(chan, f"ℹ️ {target_name} riammesso.")
                    else: send(sock, "Utente non bannato.")

            # --- MESSAGGI NORMALI ---
            else:
                if not chan: send(sock, "Usa JOIN <nome> per parlare.")
                elif nick in channels[chan]["banned"]: send(sock, "Sei bannato qui.")
                else: broadcast(chan, f"[{chan}] {nick}: {msg}", exclude=sock)

        except Exception: break

    # --- DISCONNESSIONE ---
    with lock:
        if sock in clients:
            leave_channel(sock)
            del clients[sock]
    
    sock.close()
    print(f"[-] {addr} disconnesso")

# ----------------------------------------------------------
# MAIN
# ----------------------------------------------------------
if __name__ == "__main__":
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("0.0.0.0", 4000))
    s.listen(50)
    print("Server (v2.0 Fixed) avviato su porta 4000...")

    while True:
        conn, addr = s.accept()
        threading.Thread(target=handle_client, args=(conn, addr), daemon=True).start()