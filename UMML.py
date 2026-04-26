import os
import json
import shutil
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk, colorchooser
import sqlite3
import subprocess
import re
import winreg
import struct
from pathlib import Path
modloader_version = "1.4.2"
required_keys = ["mod_version", "title", "description", "modloader_version"]

# --- Check dependency ---
def install_package(package):
    subprocess.check_call([sys.executable, "-m", "pip", "install", package])
try:
    import UnityPy
    import vdf
    import apsw
    import yaml
except ImportError:
    rootuni = tk.Tk()
    rootuni.withdraw()

    if messagebox.askyesno(
        "Tazuna saying",
        "Missing dependency. Install now?"
    ):
        try:
            install_package("unitypy")
            install_package("vdf")
            install_package("apsw-sqlite3mc")
            install_package("pyyaml")
            messagebox.showinfo(
                "Installed",
                "Please restart the application."
            )
            sys.exit(0)
        except Exception as e:
            messagebox.showerror("Error", str(e))
            sys.exit(1)
    else:
        messagebox.showwarning(
            "Not installed",
            "please try again."
        )
        sys.exit(0)
print("[OK] UnityPy ready")
print("[OK] vdf ready")
print("[OK] apsw-sqlite3mc ready")
print("[OK] pyyaml")

def find_dmm_umamusume():
    try:
        config_path = Path(os.environ.get("APPDATA", "")) / "dmmgameplayer5" / "dmmgame.cnf"

        if not config_path.is_file():
            return None

        with open(config_path, "r", encoding="utf-8") as f:
            game_data = json.load(f)

        for game in game_data.get("contents", []):
            if (
                game.get("productId") == "umamusume"
                and game.get("detail", {}).get("installed") is True
            ):
                path = game.get("detail", {}).get("path")

                if path and os.path.isdir(path):
                    return path

    except Exception as e:
        print(f"DMM detection error: {e}")

    return None

# ---------------------------
# Steam Path Detection
# ---------------------------

def get_steam_path():
    possible_keys = [
        r"SOFTWARE\WOW6432Node\Valve\Steam",
        r"SOFTWARE\Valve\Steam"
    ]

    for key_path in possible_keys:
        try:
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path)
            return winreg.QueryValueEx(key, "InstallPath")[0]
        except FileNotFoundError:
            continue

    return None


# ---------------------------
# Get Steam Libraries Properly
# ---------------------------

def get_steam_libraries(steam_path):
    libraries = []

    vdf_path = os.path.join(steam_path, "steamapps", "libraryfolders.vdf")
    if not os.path.exists(vdf_path):
        return [steam_path]

    with open(vdf_path, "r", encoding="utf-8") as f:
        data = vdf.load(f)

    folders = data.get("libraryfolders", {})

    for key in folders:
        if key.isdigit():
            path = folders[key].get("path")
            if path:
                libraries.append(path)

    return libraries


# ---------------------------
# Find Game Path
# ---------------------------

def find_game_path(app_id):
    steam_path = get_steam_path()
    if not steam_path:
        return None

    libraries = get_steam_libraries(steam_path)

    for lib in libraries:
        manifest = os.path.join(lib, "steamapps", f"appmanifest_{app_id}.acf")

        if os.path.exists(manifest):
            with open(manifest, "r", encoding="utf-8") as f:
                data = vdf.load(f)

            installdir = data.get("AppState", {}).get("installdir")
            if installdir:
                return os.path.join(lib, "steamapps", "common", installdir)

    return None

def load_settings():
    steam_game_path_jpn = find_game_path(3564400)
    dmm_game_path_jpn = find_dmm_umamusume()

    base_path_steam_en = (
        Path.home()
        / "AppData"
        / "LocalLow"
        / "Cygames"
        / "umamusume"
    )
    print(f"Steam EN path: {base_path_steam_en}")
    base_path_steam_jp = None
    if steam_game_path_jpn:
        base_path_steam_jp = (
            Path(steam_game_path_jpn)
            / "UmamusumePrettyDerby_Jpn_Data"
            / "Persistent"
        )
    print(f"Steam JP path: {base_path_steam_jp}")
    base_path_dmm_jp = None
    if dmm_game_path_jpn:
        base_path_dmm_jp = (
            Path(dmm_game_path_jpn)
            / "umamusume_Data"
            / "Persistent"
        )
    print(f"DMM Game path: {dmm_game_path_jpn}")
    root = tk.Tk()
    root.withdraw()

    # --------------------
    # Region Selection
    # --------------------
    choice_region = messagebox.askyesnocancel(
        "Select Region",
        "Select Umamusume region to load:\n\n"
        "Yes  → Global\n"
        "No   → Japan\n"
        "Cancel → Exit"
    )

    if choice_region is None:
        root.destroy()
        sys.exit(0)

    # --------------------
    # Global
    # --------------------
    if choice_region:
        base_path = base_path_steam_en
        region = "Global"

    # --------------------
    # Japan
    # --------------------
    else:
        choice_platform = messagebox.askyesnocancel(
            "DMM",
            "Are you using the DMM version?"
        )

        if choice_platform is None:
            root.destroy()
            sys.exit(0)

        if choice_platform:  # DMM
            base_path = base_path_dmm_jp
        else:  # Steam
            base_path = base_path_steam_jp

        region = "Japan"

    root.destroy()

    # --------------------
    # Validate
    # --------------------
    if not base_path or not os.path.isdir(base_path):
        messagebox.showerror(
            "Game Not Found",
            f"Selected {region} version was not found.\n\n"
            "Please make sure the game is installed and run at least once."
        )
        sys.exit(1)

    dat = os.path.join(base_path, "dat")
    backup = os.path.join(base_path, "dat.backup")

    return dat, backup, region
    
# using ref from noccu/hachimi-tools
def load_or_decrypt_meta_simple(dat_path, region):
    base_path = os.path.dirname(dat_path)
    meta_enc = os.path.join(base_path, "meta")

    if not os.path.isfile(meta_enc):
        raise RuntimeError("meta file not found")

    # decrypted filename tied to meta size (auto update)
    size = os.path.getsize(meta_enc)
    meta_dec = os.path.join(base_path, f"meta_decrypted_{size}")

    # correct DB keys
    DB_KEY_GLOBAL = "a713a5c79dbc9497c0a88669"
    DB_KEY_JP = "9c2bab97bcf8c0c4f1a9ea7881a213f6c9ebf9d8d4c6a8e43ce5a259bde7e9fd"

    DB_KEY = DB_KEY_GLOBAL if region == "Global" else DB_KEY_JP

    def can_open_plain(path):
        try:
            conn = apsw.Connection(path)
            conn.execute("SELECT name FROM sqlite_master LIMIT 1")
            conn.close()
            return True
        except Exception:
            return False

    # already decrypted / usable
    if can_open_plain(meta_enc):
        print("Meta already usable")
        return meta_enc

    # decrypted cache exists
    if os.path.isfile(meta_dec):
        print("Using cached decrypted meta")
        return meta_dec

    print("Decrypting meta database...")

    try:
        # open encrypted DB
        uri = f"file:{meta_enc}?hexkey={DB_KEY}"
        conn = apsw.Connection(uri, apsw.SQLITE_OPEN_URI | apsw.SQLITE_OPEN_READONLY)

        # export decrypted copy
        conn.execute(f"VACUUM INTO 'file:{meta_dec}?key='")
        conn.close()

    except Exception as e:
        raise RuntimeError(f"Meta decryption failed: {e}")

    return meta_dec
    
class ModLoaderGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("UMML GUI")

        self.dat_path, self.backup_path, self.region = load_settings()
        # bind function (optional but matches your request)
        self.meta_path_load = load_or_decrypt_meta_simple
        # resolve meta path ONCE at startup
        self.meta_path = self.meta_path_load(self.dat_path, self.region)   
        #print(f"[Meta] Using meta DB: {self.meta_path}")
        self.mod_path = tk.StringVar()
        self.title_text = tk.StringVar()
        self.version_text = tk.StringVar()

        self.create_widgets()

    def create_widgets(self):
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)
        misc_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Misc", menu=misc_menu)
        character_menu = tk.Menu(misc_menu, tearoff=0)
        misc_menu.add_cascade(label="Character", menu=character_menu)

        character_menu.add_command(
            label="Attribute",
            command=self.open_chara_settings
        )

        character_menu.add_command(
            label="Personality",
            command=self.open_personality_settings
        )

        character_menu.add_command(
            label="Dress",
            command=self.open_dress_settings
        )
        
        single_mode_menu = tk.Menu(misc_menu, tearoff=0)
        misc_menu.add_cascade(label="Single Mode", menu=single_mode_menu)

        single_mode_menu.add_command(
            label="Training",
            command=self.open_training_settings
        )
        experimental_menu = tk.Menu(misc_menu, tearoff=0)
        misc_menu.add_cascade(label="EXPERIMENTAL", menu=experimental_menu)

        experimental_menu.add_command(
            label="Merge Translation from Global to Japanese",
            command=self.force_translate_english
        )
        
        modelreplace_menu = tk.Menu(misc_menu, tearoff=0)
        misc_menu.add_cascade(label="umamusume-model-replace", menu=modelreplace_menu)

        modelreplace_menu.add_command(
            label="Swap Character",
            command=self.open_swap_character
        )

        mod_frame = tk.LabelFrame(self.root, text="Mod Loader")
        mod_frame.pack(fill="x", padx=10, pady=5)
        tk.Entry(mod_frame, textvariable=self.mod_path, width=60).pack(side="left", padx=5)
        tk.Button(mod_frame, text="Browse", command=self.browse_folder).pack(side="left")
        tk.Button(mod_frame, text="Reload", command=self.reload).pack(side="left", padx=5)
        tk.Button(mod_frame, text="Preview", command=self.preview_assets).pack(side="left", padx=5)
        info_frame = tk.LabelFrame(self.root, text="Information")
        info_frame.pack(fill="x", padx=10, pady=5)
        tk.Label(info_frame, textvariable=self.title_text).pack(anchor="w")
        tk.Label(info_frame, textvariable=self.version_text).pack(anchor="w")
        self.description_box = tk.Text(info_frame, height=8, width=70, state="disabled")
        self.description_box.pack()

        control_frame = tk.LabelFrame(self.root, text="Controls")
        control_frame.pack(fill="x", padx=10, pady=5)
        self.assets_load_btn = tk.Button(control_frame, text="Load Assets", state="disabled", command=self.load_assets)
        self.assets_load_btn.pack(side="left", padx=5)
        self.assets_load_raw_btn = tk.Button(control_frame, text="Load Assets (manual)", command=self.load_assets_manual)
        self.assets_load_raw_btn.pack(side="left", padx=5)
        #self.assets_unload_btn = tk.Button(control_frame, text="Unload Assets", state="disabled", command=self.unload_assets)
        #self.assets_unload_btn.pack(side="left", padx=5)
        tk.Label(control_frame, text=f"Version : {modloader_version}").pack(side="right")
        tk.Label(control_frame, text=f"Region : {self.region} |").pack(side="right")
        self.restore_btn = tk.Button(control_frame, text="Restore Assets", command=self.restore_original_assets)
        self.restore_btn.pack(side="left", padx=5)
        self.delete_db_btn = tk.Button(control_frame, text="Delete Database", command=self.delete_master_db)
        self.delete_db_btn.pack(side="left", padx=5)
        progress_frame = tk.LabelFrame(self.root, text="Progress")
        progress_frame.pack(fill="x", padx=10, pady=5)
        self.progress_label = tk.Label(progress_frame, text="Waiting")
        self.progress_label.pack(anchor="w")
        self.progress_bar = ttk.Progressbar(progress_frame, orient="horizontal", length=400, mode="determinate")
        self.progress_bar.pack()
        
    # from kairusds/umamusu-utils
    def decrypt_assets_internal(self, src_root, dst_root, use_hash=False, filter_path=None):
        AB_KEY = b'\x53\x2B\x46\x31\xE4\xA7\xB9\x47\x3E\x7C\xFB'

        def derive_asset_key(key_long):
            if key_long == 0:
                return None
            key_bytes = struct.pack('<q', key_long)
            base_key = AB_KEY
            base_len = len(base_key)
            final_key = bytearray(base_len * 8)

            for i in range(base_len):
                b = base_key[i]
                base_offset = i * 8
                for j in range(8):
                    final_key[base_offset + j] = b ^ key_bytes[j]
            return bytes(final_key)

        # --- select meta DB ---
        meta_db = self.meta_path

        if not os.path.isfile(meta_db):
            raise RuntimeError("Meta database not found")

        os.makedirs(dst_root, exist_ok=True)

        conn = sqlite3.connect(meta_db)
        c = conn.cursor()

        # DRIVE FROM MOD FILES
        all_paths = list(self.scan_full_path(src_root))

        # ---------------- FILTER ----------------
        if filter_path:
            filtered = []
            for p in all_paths:
                parts = p.replace("\\", "/").split("/")
                if filter_path in parts:
                    filtered.append(p)
            all_paths = filtered
            #print(f"filtered: {all_paths}")
            
        total = len(all_paths)
        self.progress_bar["maximum"] = total
        self.progress_bar["value"] = 0

        decoded_count = 0
        missing_meta = 0

        for i, rel_path in enumerate(all_paths, start=1):
            input_path = os.path.join(src_root, rel_path)
            self.progress_label.config(
                text=f"Encrypting Asset {i} / {total}"
            )
            self.progress_bar["value"] = i
            self.root.update_idletasks()

            if use_hash:
                # input files are hashes
                c.execute("SELECT e FROM a WHERE h=?", (rel_path,))
                row = c.fetchone()
                if not row:
                    missing_meta += 1
                    continue

                hash_name = rel_path
                enc_key = int(row[0])
            else:
                # input files are meta paths
                c.execute("SELECT h, e FROM a WHERE n=?", (rel_path,))
                row = c.fetchone()
                # fallback unity
                if not row:
                    #print(f"{rel_path} not found, looking up")
                    try:
                        with open(input_path, "rb") as f:
                            header = f.read(8)
                            if header.startswith(b"UnityFS"):
                                f.seek(0)
                                env = UnityPy.load(f)

                                for obj in env.objects:
                                    if obj.type.name == "AssetBundle":
                                        data = obj.read()
                                        if data.m_Name:
                                            resolved_name = os.path.splitext(data.m_Name)[0]
                                            # retry lookup
                                            c.execute("SELECT h, e FROM a WHERE n=?", (resolved_name,))
                                            row = c.fetchone()
                                            if row:
                                                #print(f"{row} is found!, breaking")
                                                break
                    except Exception:
                        pass
                # FINAL CHECK
                if not row:
                    missing_meta += 1
                    continue

                hash_name, enc_key = row[0], int(row[1])

            output_path = os.path.join(dst_root, hash_name)
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            # for audio / usm
            if enc_key == 0:
                shutil.copy(input_path, output_path)
            else:
                with open(input_path, "rb") as f:
                    data = bytearray(f.read())

                if len(data) > 256:
                    key = derive_asset_key(enc_key)
                    if key:
                        klen = len(key)
                        for i in range(256, len(data)):
                            data[i] ^= key[i % klen]

                with open(output_path, "wb") as f:
                    f.write(data)
            decoded_count += 1

        conn.close()
        return decoded_count, missing_meta   

    def swap_character_attributes(self, src_cid, dst_cid):
        master_db = os.path.join(
            os.path.dirname(self.dat_path),
            "master",
            "master.mdb"
        )

        conn = sqlite3.connect(master_db)
        c = conn.cursor()

        c.execute("""
            CREATE TABLE IF NOT EXISTS chara_type_bak AS
            SELECT * FROM chara_type
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS chara_data_bak AS
            SELECT * FROM chara_data
        """)

        c.execute("""
            SELECT target_scene, target_cut, target_type, value
            FROM chara_type_bak
            WHERE chara_id=?
            ORDER BY CAST(id AS INTEGER)
        """, (src_cid,))
        source_rows = c.fetchall()

        for ts, tc, tt, val in source_rows:
            c.execute("""
                UPDATE chara_type
                SET value=?
                WHERE chara_id=?
                  AND target_scene=?
                  AND target_cut=?
                  AND target_type=?
            """, (val, dst_cid, ts, tc, tt))

        columns_to_copy = [
            "sex",
            "image_color_main",
            "image_color_sub",
            "ui_color_main",
            "ui_color_sub",
            "ui_training_color_1",
            "ui_training_color_2",
            "ui_border_color",
            "ui_num_color_1",
            "ui_num_color_2",
            "ui_turn_color",
            "ui_wipe_color_1",
            "ui_wipe_color_2",
            "ui_wipe_color_3",
            "ui_speech_color_1",
            "ui_speech_color_2",
            "ui_nameplate_color_1",
            "ui_nameplate_color_2",
            "height",
            "bust",
            "scale",
            "skin",
            "shape",
            "socks",
            "race_running_type",
            "ear_random_time_min",
            "ear_random_time_max",
            "tail_random_time_min",
            "tail_random_time_max",
            "story_ear_random_time_min",
            "story_ear_random_time_max",
            "story_tail_random_time_min",
            "story_tail_random_time_max",
            "mini_mayu_shader_type"
        ]

        # read source values
        c.execute(
            f"SELECT {', '.join(columns_to_copy)} FROM chara_data_bak WHERE id=?",
            (src_cid,)
        )
        src_values = c.fetchone()

        if src_values:
            set_clause = ", ".join([f"{col}=?" for col in columns_to_copy])

            c.execute(
                f"UPDATE chara_data SET {set_clause} WHERE id=?",
                (*src_values, dst_cid)
            )

        conn.commit()
        conn.close()

    def open_swap_character(self):
        master_db = os.path.join(os.path.dirname(self.dat_path), "master", "master.mdb")

        conn = sqlite3.connect(master_db)
        c = conn.cursor()
        c.execute("SELECT id FROM dress_data WHERE id BETWEEN 100000 AND 1000000 ORDER BY id")
        ids = [r[0] for r in c.fetchall()]

        options = []
        for oid in ids:
            c.execute("SELECT text FROM text_data WHERE category=14 AND `index`=?", (oid,))
            name = c.fetchone()
            name = name[0] if name else "Unknown"

            c.execute("SELECT text FROM text_data WHERE category=15 AND `index`=?", (oid,))
            detail = c.fetchone()
            detail = detail[0] if detail else ""

            options.append(f"{oid} - {name} - {detail}")

        conn.close()

        win = tk.Toplevel(self.root)
        win.title("Swap Character")

        tk.Label(win, text="Source").pack(anchor="w", padx=10)
        src_var = tk.StringVar()
        ttk.Combobox(win, textvariable=src_var, values=options, width=60).pack(padx=10)

        tk.Label(win, text="Target").pack(anchor="w", padx=10, pady=(10,0))
        dst_var = tk.StringVar()
        ttk.Combobox(win, textvariable=dst_var, values=options, width=60).pack(padx=10)

        body_var = tk.BooleanVar(value=True)
        head_var = tk.BooleanVar(value=True)
        tail_var = tk.BooleanVar(value=True)
        tk.Checkbutton(win, text="Body", variable=body_var).pack(anchor="w", padx=20, side="left")
        tk.Checkbutton(win, text="Head", variable=head_var).pack(anchor="w", padx=20, side="left")
        tk.Checkbutton(win, text="Tail (texture / attribute)", variable=tail_var).pack(anchor="w", padx=20, side="left")
        chibi_body_var = tk.BooleanVar(value=False)
        chibi_head_var = tk.BooleanVar(value=False)
        attr_var = tk.BooleanVar(value=True)

        tk.Checkbutton(win, text="Chibi Body", variable=chibi_body_var).pack(anchor="w", padx=20)
        tk.Checkbutton(win, text="Chibi Head (fix softlock)", variable=chibi_head_var).pack(anchor="w", padx=20)
        tk.Checkbutton(win, text="Attribute", variable=attr_var).pack(anchor="w", padx=20, side="left")
        def run():
            if not src_var.get() or not dst_var.get():
                messagebox.showerror("Error", "Select source and target")
                return

            src_oid = int(src_var.get().split(" - ")[0])
            dst_oid = int(dst_var.get().split(" - ")[0])

            self.swap_character(
                src_oid,
                dst_oid,
                body_var.get(),
                head_var.get(),
                attr_var.get(),
                chibi_body_var.get(),
                chibi_head_var.get(),
                tail_var.get()
            )

        tk.Button(win, text="Swap", command=run).pack(pady=10)

    def swap_character(self, src_oid, dst_oid, do_body, do_head, do_attribute,
                       do_chibi_body, do_chibi_head, do_tail):

        def normalize_body_path(path, chara_id, sub_id):
            """
            remove chara specific portion so structures can be compared
            """
            token = f"bdy{chara_id}_{sub_id}"
            return path.replace(token, "bdyXXXX_XX")

        def normalize_head_path(path, chara_id, sub_id):
            token = f"chr{chara_id}_{sub_id}"
            return path.replace(token, "chrXXXX_XX")
            
        def normalize_mbdy(path, cid, sid):
            return path.replace(f"mbdy{cid}_{sid}", "mbdyXXXX_XX")
            
        def normalize_tail_tex(path, tail_id, chara_id):
            return path.replace(f"_{chara_id}_", "_XXXX_")
            
        def normalize_mchr(path, cid, sid):
            return path.replace(f"mchr{cid}_{sid}", "mchrXXXX_XX")

        def swap_bytes(data, a, b):
            placeholder = b"__TMP_SWAP__"
            data = data.replace(a, placeholder)
            data = data.replace(b, a)
            data = data.replace(placeholder, b)
            return data
            
        # ---- CHIBI SOFTLOCK WARNING ----
        if do_body and do_head and not do_chibi_head:
            proceed = messagebox.askyesno(
                "Rig Compatibility Warning",
                "Swapping Body + Head may break animation bindings.\n"
                "If the rigs differ, the game can freeze during animations.\n\n"
                "Some combinations work without issues,\n"
                "but others may cause softlock.\n\n"
                "Swapping Chibi Head is recommended.\n\n"
                "Continue anyway?"
            )
            if not proceed:
                return
        tmp_root = "UMML_tmp"
        raw_dir = os.path.join(tmp_root, "raw")
        dec_dir = os.path.join(tmp_root, "dec")

        shutil.rmtree(tmp_root, ignore_errors=True)
        os.makedirs(raw_dir, exist_ok=True)
        os.makedirs(dec_dir, exist_ok=True)

        # -------- GET CHARACTER INFO --------
        master = sqlite3.connect(
            os.path.join(os.path.dirname(self.dat_path), "master", "master.mdb")
        )
        mc = master.cursor()

        mc.execute("SELECT chara_id, body_type_sub, head_sub_id FROM dress_data WHERE id=?", (src_oid,))
        chara_src, sub_src, sub_head_src = mc.fetchone()

        mc.execute("SELECT chara_id, body_type_sub, head_sub_id FROM dress_data WHERE id=?", (dst_oid,))
        chara_dst, sub_dst, sub_head_dst = mc.fetchone()
        if do_tail:
            mc.execute("SELECT tail_model_id FROM chara_data WHERE id=?", (chara_src,))
            src_tail = mc.fetchone()[0]

            mc.execute("SELECT tail_model_id FROM chara_data WHERE id=?", (chara_dst,))
            dst_tail = mc.fetchone()[0]
            swap_tail_assets = False
            src_tail_str = f"{int(src_tail):04d}"
            dst_tail_str = f"{int(dst_tail):04d}"
            # --- rule: no tail model ---
            if src_tail == -1:
                # update DB only later
                pass

            # --- same model: safe ---
            elif src_tail == dst_tail:
                swap_tail_assets = True

            # --- different model ---
            else:
                proceed = messagebox.askyesno(
                    "Tail Model Difference",
                    "The characters use different tail models.\n\n"
                    "Tail texture cannot be swapped.\n"
                    "The source tail appearance will be kept.\n\n"
                    "Continue?"
                )
                if not proceed:
                    return
        mc.execute("SELECT attachment_model_id FROM chara_data WHERE id=?", (chara_src,))
        src_attach = mc.fetchone()[0]

        mc.execute("SELECT attachment_model_id FROM chara_data WHERE id=?", (chara_dst,))
        dst_attach = mc.fetchone()[0]
        if src_attach != dst_attach:
            proceed_attach = messagebox.askyesno(
                "Nail Color Notice",
                "Nail color cannot be swapped.\n\n"
                "Target will use its default nail color.\n\n"
                "Continue?"
            )
            if not proceed_attach:
                return
        sub_src = f"{int(sub_src):02d}"
        sub_dst = f"{int(sub_dst):02d}"
        sub_head_src = f"{int(sub_head_src):02d}"
        sub_head_dst = f"{int(sub_head_dst):02d}"
        # print(f"{chara_src}")
        # print(f"{chara_dst}")
        # print(f"{sub_src}")
        # print(f"{sub_dst}")
        # print(f"{sub_head_src}")
        # print(f"{sub_head_dst}")
        master.close()

        meta = sqlite3.connect(self.meta_path)
        c = meta.cursor()

        def get_tail_textures(tail_id, chara_id):
            pattern = (
                f"3d/chara/tail/tail{tail_id}_00/textures/"
                f"tex_tail{tail_id}_00_{chara_id}_%"
            )
            c.execute("SELECT n FROM a WHERE n LIKE ?", (pattern,))
            return {r[0] for r in c.fetchall()}

        def get_assets(pattern):
            """
            Returns both normal asset paths AND sourceresources paths
            """
            results = set()

            # normal assets
            c.execute("SELECT n FROM a WHERE n LIKE ?", (pattern,))
            results |= {r[0] for r in c.fetchall()}

            # sourceresources assets
            c.execute(
                "SELECT n FROM a WHERE n LIKE ?",
                ("sourceresources/" + pattern,)
            )
            results |= {r[0] for r in c.fetchall()}

            return results

        assets_src = set()
        assets_dst = set()
        tail_src_assets = set()
        tail_dst_assets = set()


        if do_body:
            assets_src |= get_assets(f"3d/chara/body/bdy{chara_src}_{sub_src}%")
            assets_dst |= get_assets(f"3d/chara/body/bdy{chara_dst}_{sub_dst}%")

        if do_head:
            assets_src |= get_assets(f"3d/chara/head/chr{chara_src}_{sub_head_src}%")
            assets_dst |= get_assets(f"3d/chara/head/chr{chara_dst}_{sub_head_dst}%")
            
        if do_chibi_body:
            assets_src |= get_assets(f"3d/chara/mini/body/mbdy{chara_src}_{sub_src}%")
            assets_dst |= get_assets(f"3d/chara/mini/body/mbdy{chara_dst}_{sub_dst}%")

        if do_chibi_head:
            assets_src |= get_assets(f"3d/chara/mini/head/mchr{chara_src}_{sub_head_src}%")
            assets_dst |= get_assets(f"3d/chara/mini/head/mchr{chara_dst}_{sub_head_dst}%")
            
        if do_tail:
            if swap_tail_assets:
                tail_src_assets = get_tail_textures(src_tail_str, chara_src)
                tail_dst_assets = get_tail_textures(dst_tail_str, chara_dst)

                assets_src |= tail_src_assets
                assets_dst |= tail_dst_assets
                
        # -------- VERIFY MATCH --------
        src_struct = set()
        dst_struct = set()

        if do_body:
            src_names = get_assets(f"3d/chara/body/bdy{chara_src}_{sub_src}%")
            dst_names = get_assets(f"3d/chara/body/bdy{chara_dst}_{sub_dst}%")

            for p in src_names:
                src_struct.add(normalize_body_path(p, chara_src, sub_src))

            for p in dst_names:
                dst_struct.add(normalize_body_path(p, chara_dst, sub_dst))


        if do_head:
            src_names = get_assets(f"3d/chara/head/chr{chara_src}_{sub_head_src}%")
            dst_names = get_assets(f"3d/chara/head/chr{chara_dst}_{sub_head_dst}%")

            for p in src_names:
                src_struct.add(normalize_head_path(p, chara_src, sub_head_src))

            for p in dst_names:
                dst_struct.add(normalize_head_path(p, chara_dst, sub_head_dst))
                
        if do_chibi_body:
            for p in get_assets(f"3d/chara/mini/body/mbdy{chara_src}_{sub_src}%"):
                src_struct.add(normalize_mbdy(p, chara_src, sub_src))
            for p in get_assets(f"3d/chara/mini/body/mbdy{chara_dst}_{sub_dst}%"):
                dst_struct.add(normalize_mbdy(p, chara_dst, sub_dst))

        if do_chibi_head:
            for p in get_assets(f"3d/chara/mini/head/mchr{chara_src}_{sub_head_src}%"):
                src_struct.add(normalize_mchr(p, chara_src, sub_head_src))
            for p in get_assets(f"3d/chara/mini/head/mchr{chara_dst}_{sub_head_dst}%"):
                dst_struct.add(normalize_mchr(p, chara_dst, sub_head_dst))
        if do_tail:
            if swap_tail_assets:
                src_struct |= {normalize_tail_tex(p, src_tail_str, chara_src) for p in tail_src_assets}
                dst_struct |= {normalize_tail_tex(p, dst_tail_str, chara_dst) for p in tail_dst_assets}
                    
        missing = src_struct - dst_struct

        # -------- VERIFY RESULT --------
        if missing:
            print("Missing matching assets:")
            for m in sorted(missing):
                print("  ", m)

            proceed1 = messagebox.askyesno(
                "Structural Mismatch Detected",
                f"{len(missing)} assets are missing in target.\n\n"
                "This can cause:\n"
                "- Invisible body parts\n"
                "- Broken mesh\n"
                "- Texture errors\n"
                "- Game crash\n\n"
                "Do you want to swap anyway?"
            )

            if not proceed1:
                messagebox.showinfo("Swap Cancelled", "Swap aborted for safety.")
                return
        else:
            proceed1 = messagebox.askyesno(
                "Structure Verified",
                "No structural differences detected.\n\n"
                "Do you want to proceed with swap?"
            )

            if not proceed1:
                messagebox.showinfo("Swap Cancelled", "Swap aborted.")
                return
        
        # -------- COPY GAME FILES --------
        save_folder = filedialog.askdirectory(title="Select folder to save mod")
        if not save_folder:
            shutil.rmtree(tmp_root, ignore_errors=True)
            return
        meta.close()
        meta = sqlite3.connect(self.meta_path)
        c = meta.cursor()

        copied = 0

        all_assets = assets_src | assets_dst

        for asset_name in all_assets:
            # get hash from meta
            c.execute("SELECT h FROM a WHERE n=?", (asset_name,))
            row = c.fetchone()
            if not row:
                continue

            asset_hash = row[0]

            src_path = os.path.join(self.dat_path, asset_hash[:2], asset_hash)
            dst_path = os.path.join(raw_dir, asset_hash)

            if os.path.isfile(src_path):
                shutil.copy2(src_path, dst_path)
                #print(f"{src_path}")
                copied += 1
            else:
                print("missing dat:", src_path)

        meta.close()

        print(f"Copied {copied} assets")

        # -------- DECRYPT --------
        decoded_count, missing_meta = self.decrypt_assets_internal(raw_dir, dec_dir, use_hash=True, filter_path=None)

        # -------- MODIFY BUNDLES --------
        for file in os.listdir(dec_dir):
            path = os.path.join(dec_dir, file)

            with open(path, "rb") as f:
                data = f.read()

            # decompress if Unity bundle compressed
            try:
                env = UnityPy.load(data)
                data = env.file.save()
            except Exception:
                pass

            if do_body:
                a = f"bdy{chara_src}_{sub_src}".encode()
                b = f"bdy{chara_dst}_{sub_dst}".encode()
                data = swap_bytes(data, a, b)

            if do_head:
                a = f"chr{chara_src}_{sub_head_src}".encode()
                b = f"chr{chara_dst}_{sub_head_dst}".encode()
                data = swap_bytes(data, a, b)
                
            if do_chibi_body:
                a = f"mbdy{chara_src}_{sub_src}".encode()
                b = f"mbdy{chara_dst}_{sub_dst}".encode()
                data = swap_bytes(data, a, b)

            if do_chibi_head:
                a = f"mchr{chara_src}_{sub_head_src}".encode()
                b = f"mchr{chara_dst}_{sub_head_dst}".encode()
                data = swap_bytes(data, a, b)
            if do_tail:
                if swap_tail_assets:
                    a = f"tex_tail{src_tail_str}_00_{chara_src}".encode()
                    b = f"tex_tail{dst_tail_str}_00_{chara_dst}".encode()
                    data = swap_bytes(data, a, b)

            with open(path, "wb") as f:
                f.write(data)

        # -------- EXPORT AS MOD --------
        mod_name = os.path.basename(save_folder.rstrip("/\\"))
        assets_out = os.path.join(save_folder, "assets")

        os.makedirs(assets_out, exist_ok=True)
        assets = os.listdir(dec_dir)

        decoded_count = 0

        for i, file in enumerate(assets, start=1):
            src = os.path.join(dec_dir, file)
            dst = os.path.join(assets_out, file)

            shutil.copy2(src, dst)

            self.progress_label.config(text=f"Exporting {i}/{len(assets)}")
            self.progress_bar["value"] = i
            self.root.update_idletasks()

            decoded_count += 1
            
        # create setting.json
        setting_data = {
            "mod_version": "1.0.0",
            "title": mod_name,
            "description": ["generated from swap character"],
            "modloader_version": modloader_version
        }

        with open(os.path.join(save_folder, "setting.json"), "w", encoding="utf-8") as f:
            json.dump(setting_data, f, indent=4, ensure_ascii=False)

        shutil.rmtree(tmp_root, ignore_errors=True)

        messagebox.showinfo(
            "Success",
            f"Mod exported successfully.\n"
            f"{decoded_count} assets generated.\n"
            f"{missing_meta} missing in meta."
        )

    def force_translate_english(self):
        # paths
        en_base = os.path.join(
            "C:\\Users", os.getlogin(),
            "AppData", "LocalLow", "Cygames", "umamusume"
        )
        jp_base = os.path.dirname(self.dat_path)

        en_db = os.path.join(en_base, "master", "master.mdb")
        jp_db = os.path.join(jp_base, "master", "master.mdb")

        if not (os.path.isfile(en_db) and os.path.isfile(jp_db)):
            messagebox.showerror(
                "Unavailable",
                "Both Global and Japan master databases are required."
            )
            return

        if not messagebox.askyesno(
            "Force Translate English",
            "Multiple Umamusume installations detected.\n\n"
            "Do you want to load English text from Global\n"
            "and overwrite Japanese text?\n\n"
            "This affects ALL text entries."
        ):
            return

        try:
            # backup JP db
            shutil.copy(jp_db, jp_db + ".bak")

            conn_en = sqlite3.connect(en_db)
            conn_jp = sqlite3.connect(jp_db)

            c_en = conn_en.cursor()
            c_jp = conn_jp.cursor()

            # load EN text
            c_en.execute("SELECT category, `index`, text FROM text_data")
            en_map = {
                (cat, idx): text
                for cat, idx, text in c_en.fetchall()
            }

            # update JP text
            c_jp.execute("SELECT category, `index` FROM text_data")
            for cat, idx in c_jp.fetchall():
                key = (cat, idx)
                if key in en_map:
                    c_jp.execute(
                        "UPDATE text_data SET text=? WHERE category=? AND `index`=?",
                        (en_map[key], cat, idx)
                    )
            # --- character_system_text ---
            c_en.execute("""
                SELECT character_id, voice_id, cue_sheet, lip_sync_data, text
                FROM character_system_text
            """)

            char_sys_map = {
                (cid, vid, cue, lip): text
                for cid, vid, cue, lip, text in c_en.fetchall()
            }

            c_jp.execute("""
                SELECT character_id, voice_id, cue_sheet, lip_sync_data
                FROM character_system_text
            """)

            for cid, vid, cue, lip in c_jp.fetchall():
                key = (cid, vid, cue, lip)
                if key in char_sys_map:
                    c_jp.execute("""
                        UPDATE character_system_text
                        SET text=?
                        WHERE character_id=? AND voice_id=? AND cue_sheet=? AND lip_sync_data=?
                    """, (char_sys_map[key], cid, vid, cue, lip))
                    
            # --- race_jikkyo_comment ---
            c_en.execute("""
                SELECT group_id, voice, message
                FROM race_jikkyo_comment
            """)

            jikkyo_comment_map = {
                (gid, voice): msg
                for gid, voice, msg in c_en.fetchall()
            }

            c_jp.execute("""
                SELECT group_id, voice
                FROM race_jikkyo_comment
            """)

            for gid, voice in c_jp.fetchall():
                key = (gid, voice)
                if key in jikkyo_comment_map:
                    c_jp.execute("""
                        UPDATE race_jikkyo_comment
                        SET message=?
                        WHERE group_id=? AND voice=?
                    """, (jikkyo_comment_map[key], gid, voice))
                    
            # --- race_jikkyo_message ---
            c_en.execute("""
                SELECT group_id, voice, message
                FROM race_jikkyo_message
            """)

            jikkyo_message_map = {
                (gid, voice): msg
                for gid, voice, msg in c_en.fetchall()
            }

            c_jp.execute("""
                SELECT group_id, voice
                FROM race_jikkyo_message
            """)

            for gid, voice in c_jp.fetchall():
                key = (gid, voice)
                if key in jikkyo_message_map:
                    c_jp.execute("""
                        UPDATE race_jikkyo_message
                        SET message=?
                        WHERE group_id=? AND voice=?
                    """, (jikkyo_message_map[key], gid, voice))

            conn_jp.commit()
            conn_en.close()
            conn_jp.close()

            messagebox.showinfo(
                "Done",
                "Japanese text has been replaced with English.\n"
                "A backup was created: master.mdb.bak"
            )

        except Exception as e:
            messagebox.showerror("Error", str(e))

    def scan_full_path(self, base_path):
        result = []
        for root, _, files in os.walk(base_path):
            for file in files:
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, base_path)
                result.append(rel_path.replace("\\", "/"))
        return result

    def open_personality_settings(self):
        messagebox.showwarning("Tazuna saying", 
                               "NEVER swap Haru Urara with Smart Falcon!")
        db_path = os.path.join(os.path.dirname(self.dat_path), "master", "master.mdb")
        
        if not os.path.isfile(db_path):
            messagebox.showerror("Error", "master.mdb not found")
            return

        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        c.execute("""
        CREATE TABLE IF NOT EXISTS chara_type_bak AS
        SELECT * FROM chara_type
        """)
        conn.commit()
        # --- get character list ---
        c.execute("SELECT id FROM chara_data ORDER BY id")
        chara_ids = [r[0] for r in c.fetchall()]

        chara_names = {}
        for cid in chara_ids:
            c.execute("SELECT text FROM text_data WHERE `index`=? AND category=6", (cid,))
            row = c.fetchone()
            chara_names[cid] = row[0] if row else f"Chara {cid}"

        win = tk.Toplevel(self.root)
        win.title("Personality Settings")
        win.geometry("1000x500")

        canvas = tk.Canvas(win)
        scrollbar = tk.Scrollbar(win, orient="vertical", command=canvas.yview)
        frame = tk.Frame(canvas)

        frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        swap_vars = {}

        options = ["None"] + [f"{cid} - {chara_names[cid]}" for cid in chara_ids]
        # 1212
        def apply_range():
            try:
                start_id = int(start_id_var.get())
                end_id = int(end_id_var.get())
            except ValueError:
                messagebox.showerror("Error", "Start ID and End ID must be numbers.")
                return

            selected = apply_from_var.get()
            if selected == "None":
                return

            for cid, var in swap_vars.items():
                if start_id != -1 and cid < start_id:
                    continue
                if end_id != -1 and cid > end_id:
                    continue
                var.set(selected)

        for cid in chara_ids:
            row = tk.Frame(frame)
            row.pack(fill="x", pady=2)

            tk.Label(row, text=f"{cid} - {chara_names[cid]}", width=35, anchor="w").pack(side="left")

            var = tk.StringVar(value="None")
            ttk.Combobox(row, textvariable=var, values=options, state="readonly", width=30).pack(side="left")
            swap_vars[cid] = var
        # 1212    
        control_row = tk.Frame(win)
        control_row.pack(pady=5)

        tk.Label(control_row, text="Start ID").pack(side="left", padx=2)
        start_id_var = tk.StringVar(value="-1")
        tk.Entry(control_row, textvariable=start_id_var, width=6).pack(side="left")

        tk.Label(control_row, text="End ID").pack(side="left", padx=5)
        end_id_var = tk.StringVar(value="-1")
        tk.Entry(control_row, textvariable=end_id_var, width=6).pack(side="left")

        tk.Label(control_row, text="Swap To").pack(side="left", padx=5)

        apply_from_var = tk.StringVar(value="None")
        apply_combo = ttk.Combobox(
            control_row,
            textvariable=apply_from_var,
            values=options,
            state="readonly",
            width=30
        )
        apply_combo.pack(side="left", padx=5)

        tk.Button(control_row, text="Apply", command=lambda: apply_range()).pack(side="left", padx=5)
        ##
        def swap_personality():
            for target_cid, var in swap_vars.items():
                if var.get() == "None":
                    continue

                source_cid = int(var.get().split(" - ")[0])

                # --- SOURCE ---
                c.execute("""
                    SELECT target_scene, target_cut, target_type, value
                    FROM chara_type_bak
                    WHERE chara_id=?
                    ORDER BY CAST(id AS INTEGER)
                """, (source_cid,))
                source_rows = c.fetchall()

                for ts, tc, tt, v in source_rows:
                    c.execute("""
                        UPDATE chara_type
                        SET value=?
                        WHERE chara_id=?
                          AND target_scene=?
                          AND target_cut=?
                          AND target_type=?
                    """, (v, target_cid, ts, tc, tt))

            conn.commit()
            messagebox.showinfo("Done", "Personality swapped successfully.")

        tk.Button(win, text="Swap Personality", command=swap_personality).pack(pady=10)

        win.protocol("WM_DELETE_WINDOW", lambda: (conn.close(), win.destroy()))

    def open_dress_settings(self):
        messagebox.showwarning("Dream Journey saying", "...You understand, right?")
        db_path = os.path.join(os.path.dirname(self.dat_path), "master", "master.mdb")
        if not os.path.isfile(db_path):
            messagebox.showerror("Error", f"Database not found: {db_path}")
            return

        try:
            conn = sqlite3.connect(db_path)
            c = conn.cursor()
            # get dress_data rows
            c.execute("SELECT id, use_gender, body_type, body_type_sub, body_setting, head_sub_id FROM dress_data")
            dress_rows = c.fetchall()

            dress_data_list = []
            for oid, gender, body, sub, setting, head_sub in dress_rows:
                # name (cat 14)
                c.execute("SELECT text FROM text_data WHERE `index`=? AND category=14", (oid,))
                name_row = c.fetchone()
                name_text = name_row[0] if name_row else f"Dress {oid}"

                # detail (cat 15)
                c.execute("SELECT text FROM text_data WHERE `index`=? AND category=15", (oid,))
                detail_row = c.fetchone()
                detail_text = detail_row[0] if detail_row else "N/A"

                dress_data_list.append((oid, name_text, detail_text, gender, body, sub, setting, head_sub))

            conn.close()
        except Exception as e:
            messagebox.showerror("DB Error", str(e))
            return

        # --- build window ---
        win = tk.Toplevel(self.root)
        win.title("Dress Settings")
        win.geometry("1540x600")

        canvas = tk.Canvas(win)
        scrollbar = tk.Scrollbar(win, orient="vertical", command=canvas.yview)
        scroll_frame = tk.Frame(canvas)

        scroll_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # --- column headers ---
        header = tk.Frame(scroll_frame)
        header.pack(fill="x", pady=2)
        tk.Label(header, text="Dress", width=50, anchor="w", relief="ridge").pack(side="left")
        tk.Label(header, text="Gender", width=10, anchor="w", relief="ridge").pack(side="left")
        tk.Label(header, text="Body", width=10, anchor="w", relief="ridge").pack(side="left")
        tk.Label(header, text="Sub", width=10, anchor="w", relief="ridge").pack(side="left")
        tk.Label(header, text="Body Setting", width=12, anchor="w", relief="ridge").pack(side="left")
        tk.Label(header, text="Head Sub", width=10, anchor="w", relief="ridge").pack(side="left")

        # keep references for saving
        dress_vars = {}

        for oid, name_text, detail_text, gender, body, sub, setting, head_sub in dress_data_list:
            row_frame = tk.Frame(scroll_frame)
            row_frame.pack(fill="x", pady=2)

            # label
            tk.Label(row_frame, text=f"{oid} - {name_text} - {detail_text}", anchor="w", width=50).pack(side="left")

            # gender dropdown
            gender_var = tk.StringVar(value="True" if gender else "False")
            gender_combo = ttk.Combobox(row_frame, textvariable=gender_var,
                                        values=["True", "False"], state="readonly", width=8)
            gender_combo.pack(side="left", padx=2)

            # body
            body_var = tk.StringVar(value=str(body))
            tk.Entry(row_frame, textvariable=body_var, width=10).pack(side="left", padx=2)

            # sub
            sub_var = tk.StringVar(value=str(sub))
            tk.Entry(row_frame, textvariable=sub_var, width=10).pack(side="left", padx=2)

            # body setting
            setting_var = tk.StringVar(value=str(setting))
            tk.Entry(row_frame, textvariable=setting_var, width=12).pack(side="left", padx=2)
            # head sub
            head_sub_var = tk.StringVar(value=str(head_sub))
            tk.Entry(row_frame, textvariable=head_sub_var, width=10).pack(side="left", padx=2)

            dress_vars[oid] = (gender_var, body_var, sub_var, setting_var, head_sub_var)
        # --- Set All Values with Range ---
        setall_frame = tk.LabelFrame(win, text="Set All Values (Apply by ID Range)")
        setall_frame.pack(fill="x", padx=10, pady=5)

        # ID range
        tk.Label(setall_frame, text="Start ID").pack(side="left", padx=2)
        start_id_var = tk.StringVar()
        tk.Entry(setall_frame, textvariable=start_id_var, width=8).pack(side="left", padx=2)

        tk.Label(setall_frame, text="End ID").pack(side="left", padx=2)
        end_id_var = tk.StringVar()
        tk.Entry(setall_frame, textvariable=end_id_var, width=8).pack(side="left", padx=2)

        # Gender dropdown
        gender_var = tk.StringVar(value="No Change")
        gender_combo = ttk.Combobox(setall_frame, textvariable=gender_var,
                                    values=["No Change", "True", "False"],
                                    state="readonly", width=10)
        gender_combo.pack(side="left", padx=5)

        # Body
        tk.Label(setall_frame, text="Body").pack(side="left", padx=2)
        body_var = tk.StringVar()
        tk.Entry(setall_frame, textvariable=body_var, width=6).pack(side="left", padx=2)

        # Sub
        tk.Label(setall_frame, text="Sub").pack(side="left", padx=2)
        sub_var = tk.StringVar()
        tk.Entry(setall_frame, textvariable=sub_var, width=6).pack(side="left", padx=2)

        # Body Setting
        tk.Label(setall_frame, text="Body Setting").pack(side="left", padx=2)
        setting_var = tk.StringVar()
        tk.Entry(setall_frame, textvariable=setting_var, width=6).pack(side="left", padx=2)
        
        # Body Setting
        tk.Label(setall_frame, text="Head Sub").pack(side="left", padx=2)
        headsub_var = tk.StringVar()
        tk.Entry(setall_frame, textvariable=headsub_var, width=6).pack(side="left", padx=2)

        def apply_set_all_range():
            try:
                start_id = int(start_id_var.get()) if start_id_var.get().isdigit() else None
                end_id = int(end_id_var.get()) if end_id_var.get().isdigit() else None
            except ValueError:
                messagebox.showerror("Error", "Invalid ID range")
                return

            for oid, vars_tuple in dress_vars.items():
                if (start_id is not None and oid < start_id) or (end_id is not None and oid > end_id):
                    continue  # skip outside range

                g, b, s, st, hs = vars_tuple

                # gender
                if gender_var.get() != "No Change":
                    g.set(gender_var.get())

                # body
                if body_var.get().strip() != "":
                    b.set(body_var.get().strip())

                # sub
                if sub_var.get().strip() != "":
                    s.set(sub_var.get().strip())

                # body setting
                if setting_var.get().strip() != "":
                    st.set(setting_var.get().strip())

                # head
                if headsub_var.get().strip() != "":
                    hs.set(headsub_var.get().strip())

        tk.Button(setall_frame, text="Apply", command=apply_set_all_range).pack(side="left", padx=10)

        def save_all_dress():
            try:
                conn = sqlite3.connect(db_path)
                c = conn.cursor()
                for oid, vars_tuple in dress_vars.items():
                    gender_var, body_var, sub_var, setting_var, head_sub_var = vars_tuple
                    gender_val = 1 if gender_var.get() == "True" else 0
                    body_val = int(body_var.get()) if body_var.get().isdigit() else 0
                    sub_val = int(sub_var.get()) if sub_var.get().isdigit() else 0
                    setting_val = int(setting_var.get()) if setting_var.get().isdigit() else 0
                    head_sub_val = int(head_sub_var.get()) if head_sub_var.get().isdigit() else 0
                    c.execute(
                        "UPDATE dress_data SET use_gender=?, body_type=?, body_type_sub=?, body_setting=?, head_sub_id=? WHERE id=?",
                        (gender_val, body_val, sub_val, setting_val, head_sub_val, oid)
                    )
                conn.commit()
                conn.close()
                messagebox.showinfo("Success", "All dress settings saved successfully.")
            except Exception as e:
                messagebox.showerror("DB Error", str(e))

        # explanatory note
        notes_text = (
            "⚠ Note: Changing these values can cause T-pose or height issues.\n\n"
            " gender: whether this dress uses different models for male/female\n"
            "                      e.g. male = pants, female = bloomers\n"
            " body: dress category type\n"
            " sub: dress model variation\n"
            " body setting: recolor / variant of the dress\n"
            " head sub: alternate head model variant (used by chibi/SD)\n\n"
            "⚠ Important: If the chibi model for a body/sub/head combination does not exist,\n"
            "             the game may softlock when loading that dress.\n"
            "             Do NOT change 'body' or 'sub' blindly unless you know the models exist.\n"
        )
        tk.Label(win, text=notes_text, justify="left", anchor="w", fg="red").pack(fill="x", padx=10, pady=5)

        tk.Button(win, text="Save All", command=save_all_dress).pack(pady=10)

    def open_training_settings(self):
        # --- load cutin dropdown JSON ---
        messagebox.showwarning("Tazuna saying", "Do not use the towel while training. If you do, the towel will slip down.")
        cutin_json_path = os.path.join("UMML_data", "dropdown.json")
        cutin_dropdown = []
        cutin_map = {}  # id → name

        if os.path.isfile(cutin_json_path):
            try:
                import json
                with open(cutin_json_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    cutin_dropdown = data.get("cutin_file_id", [])
                    for item in cutin_dropdown:
                        cutin_map[item["id"]] = item["name"]
            except Exception as e:
                messagebox.showwarning("JSON Error", f"Failed to load dropdown.json:\n{e}")
        else:
            messagebox.showwarning("Missing JSON", "dropdown.json not found in UMML_data/")

        db_path = os.path.join(os.path.dirname(self.dat_path), "master", "master.mdb")
        if not os.path.isfile(db_path):
            messagebox.showerror("Error", f"Database not found: {db_path}")
            return

        try:
            conn = sqlite3.connect(db_path)
            c = conn.cursor()

            # --- load training rows ---
            c.execute("SELECT id, dress_id, cutin_file_id, command_type FROM single_mode_training")
            training_rows = c.fetchall()

            training_data = []
            for tid, dress_id, cutin_id, cmd_type in training_rows:
                # training name (category 138)
                c.execute("SELECT text FROM text_data WHERE `index`=? AND category=138", (tid,))
                name_row = c.fetchone()
                name_text = name_row[0] if name_row else f"Training {tid}"

                training_data.append((tid, name_text, dress_id, cutin_id, cmd_type))

            # --- build dropdown options from dress_data (id 0–1000) ---
            c.execute("SELECT id FROM dress_data WHERE id BETWEEN 0 AND 1000")
            option_ids = [row[0] for row in c.fetchall()]

            options = []
            option_map = {}
            for oid in option_ids:
                # Name
                c.execute("SELECT text FROM text_data WHERE `index`=? AND category=14", (oid,))
                name_row = c.fetchone()
                name_text = name_row[0] if name_row else f"ID {oid}"

                # Detail
                c.execute("SELECT text FROM text_data WHERE `index`=? AND category=15", (oid,))
                detail_row = c.fetchone()
                detail_text = detail_row[0] if detail_row else "N/A"

                label = f"{oid} - {name_text} - {detail_text}"
                options.append(label)
                option_map[oid] = label

            conn.close()
        except Exception as e:
            messagebox.showerror("DB Error", str(e))
            return

        # --- GUI window ---
        win = tk.Toplevel(self.root)
        win.title("Training Settings")
        win.geometry("1150x500")

        canvas = tk.Canvas(win)
        scrollbar = tk.Scrollbar(win, orient="vertical", command=canvas.yview)
        scroll_frame = tk.Frame(canvas)

        scroll_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        combo_vars = {}

        for tid, name_text, current_dress_id, current_cutin_id, cmd_type in training_data:
            row_frame = tk.Frame(scroll_frame)
            row_frame.pack(fill="x", pady=2)

            tk.Label(row_frame, text=f"{tid} - {name_text}", anchor="w", width=40).pack(side="left")

            # current selection (map dress_id to label)
            current_label = option_map.get(current_dress_id, options[0] if options else "")

            var = tk.StringVar(value=current_label)
            combo = ttk.Combobox(row_frame, textvariable=var, values=options, state="readonly", width=70)
            combo.pack(side="left", padx=5)
            # if cutin exists in json → dropdown name
            cutin_name = ""
            for item in cutin_dropdown:
                if item["id"] == current_cutin_id and item.get("command_type") == cmd_type:
                    cutin_name = item["name"]
                    break
            cutin_var = tk.StringVar(value=cutin_name)
            cutin_names = [
                item["name"]
                for item in cutin_dropdown
                if item.get("command_type") == cmd_type
            ]

            cutin_combo = ttk.Combobox(
                row_frame, textvariable=cutin_var,
                values=cutin_names, state="readonly",
                width=35
            )
            cutin_combo.pack(side="left", padx=5)
            manual_cutin_var = tk.StringVar(
                value=str(current_cutin_id) if current_cutin_id not in cutin_map else ""
            )
            tk.Entry(row_frame, textvariable=manual_cutin_var, width=10).pack(side="left", padx=5)
            combo_vars[tid] = (var, cutin_var, manual_cutin_var, cmd_type)

        def save_all_training():
            try:
                conn = sqlite3.connect(db_path)
                c = conn.cursor()

                for tid, (dress_var, cutin_var, manual_cutin_var, cmd_type) in combo_vars.items():

                    # --- extract dress ID ---
                    if dress_var.get():
                        dress_id = int(dress_var.get().split(" - ")[0])
                    else:
                        dress_id = 0

                    # --- extract cutin ---
                    cutin_value = 0

                    # dropdown selected
                    if cutin_var.get() in [item["name"] for item in cutin_dropdown]:
                        # find id by name
                        for item in cutin_dropdown:
                            if item["name"] == cutin_var.get():
                                cutin_value = item["id"]
                                break

                    # if not from dropdown → check manual entry
                    elif manual_cutin_var.get().isdigit():
                        cutin_value = int(manual_cutin_var.get())

                    c.execute(
                        "UPDATE single_mode_training SET dress_id=?, cutin_file_id=? WHERE id=?",
                        (dress_id, cutin_value, tid)
                    )

                conn.commit()
                conn.close()
                messagebox.showinfo("Success", "All training settings saved successfully.")
            except Exception as e:
                messagebox.showerror("DB Error", str(e))


        tk.Button(win, text="Save All", command=save_all_training).pack(pady=10)

    def open_chara_settings(self):
        messagebox.showwarning("Tazuna saying", 
                               "don't make everyone naughty")
        db_path = os.path.join(os.path.dirname(self.dat_path), "master", "master.mdb")
        if not os.path.isfile(db_path):
            messagebox.showerror("Error", "master.mdb not found")
            return

        conn = sqlite3.connect(db_path)
        c = conn.cursor()

        # ensure backup table exists
        c.execute("""
            CREATE TABLE IF NOT EXISTS chara_data_bak AS
            SELECT * FROM chara_data
        """)
        conn.commit()

        # load characters
        c.execute("SELECT * FROM chara_data ORDER BY id")
        rows = c.fetchall()

        # get column names dynamically
        c.execute("PRAGMA table_info(chara_data)")
        columns = [col[1] for col in c.fetchall()]

        col_index = {name: i for i, name in enumerate(columns)}

        win = tk.Toplevel(self.root)
        win.title("Character Settings")
        win.geometry("900x700")

        canvas = tk.Canvas(win)
        scrollbar = tk.Scrollbar(win, orient="vertical", command=canvas.yview)
        frame = tk.Frame(canvas)

        frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        chara_vars = {}

        for row in rows:
            cid = row[col_index["id"]]

            # get name
            c.execute("SELECT text FROM text_data WHERE category=6 AND `index`=?", (cid,))
            name_row = c.fetchone()
            name = name_row[0] if name_row else f"Chara {cid}"

            container = tk.Frame(frame, relief="groove", bd=1)
            container.pack(fill="x", pady=4, padx=5)

            header_btn = tk.Button(
                container,
                text=f"▶ {cid} - {name}",
                anchor="w",
                relief="flat"
            )
            header_btn.pack(fill="x")

            detail = tk.Frame(container)

            # ---------------- DROPDOWNS ---------------- #

            def add_dropdown(label, column, options_dict):
                tk.Label(detail, text=label, width=20, anchor="w").pack()
                var = tk.StringVar()
                current_val = row[col_index[column]]
                display = options_dict.get(current_val, list(options_dict.values())[0])
                var.set(display)

                combo = ttk.Combobox(detail, textvariable=var,
                                     values=list(options_dict.values()),
                                     state="readonly", width=30)
                combo.pack()
                return var

            sex_var = add_dropdown("Sex", "sex", {
                1: "Male",
                2: "Female"
            })

            height_var = add_dropdown("Height", "height", {
                0: "0 - Shorter",
                1: "1 - Default",
                2: "2 - Taller"
            })

            shape_var = add_dropdown("Shape", "shape", {
                0: "0 - Standard",
                1: "1 - Slim",
                2: "2 - Thicc"
            })

            skin_var = add_dropdown("Skin", "skin", {
                0: "0 - White",
                1: "1 - Peach",
                2: "2 - Yellow",
                3: "3 - Brown"
            })

            bust_var = add_dropdown("Bust", "bust", {
                0: "0 - Very Small",
                1: "1 - Small",
                2: "2 - Medium",
                3: "3 - Large",
                4: "4 - Very Large"
            })

            socks_var = add_dropdown("Socks", "socks", {
                0: "0 - None",
                1: "1 - HighSocksWhite",
                2: "2 - HighSocksBlack",
                3: "3 - KneeSocksWhite",
                4: "4 - KneeSocksBlack",
                5: "5 - TightsWhite",
                6: "6 - TightsBlack",
                7: "7 - TightsBrown"
            })

            race_var = add_dropdown("Race Running Type", "race_running_type", {
                0: "0 - Base",
                1: "1 - Pitch",
                2: "2 - Stride"
            })

            eyebrow_var = add_dropdown("Chibi Eyebrow Shader", "mini_mayu_shader_type", {
                0: "0 - Unlit",
                1: "1 - Toon",
                2: "2 - NolineToon",
                3: "3 - DitherToon"
            })

            # ---------------- CHECKBOX LOGIC ---------------- #

            current_tail = row[col_index["tail_model_id"]]

            c.execute("SELECT tail_model_id FROM chara_data_bak WHERE id=?", (cid,))
            tail_backup = c.fetchone()[0]

            tail_var = tk.BooleanVar()

            tail_cb = tk.Checkbutton(
                detail,
                text="Enable Tail",
                variable=tail_var
            )
            tail_cb.pack(anchor="w")

            # ----- state logic -----

            if current_tail == -1 and tail_backup == -1:
                # nothing exists → disable
                tail_var.set(False)
                tail_cb.config(state="disabled")

            elif current_tail == -1:
                # currently disabled
                tail_var.set(False)

            else:
                # currently enabled
                tail_var.set(True)

            current_attach = row[col_index["attachment_model_id"]]

            c.execute("SELECT attachment_model_id FROM chara_data_bak WHERE id=?", (cid,))
            attach_backup = c.fetchone()[0]

            attach_var = tk.BooleanVar()

            attach_cb = tk.Checkbutton(
                detail,
                text="Custom Nail",
                variable=attach_var
            )
            attach_cb.pack(anchor="w")

            if current_attach == -1 and attach_backup == -1:
                attach_var.set(False)
                attach_cb.config(state="disabled")

            elif current_attach == -1:
                attach_var.set(False)

            else:
                attach_var.set(True)

            # ---------------- COLOR PICKER ---------------- #

            color_columns = [
                "image_color_main",
                "image_color_sub",
                "ui_color_main",
                "ui_color_sub",
                "ui_training_color_1",
                "ui_training_color_2",
                "ui_border_color",
                "ui_num_color_1",
                "ui_num_color_2",
                "ui_turn_color",
                "ui_wipe_color_1",
                "ui_wipe_color_2",
                "ui_wipe_color_3",
                "ui_speech_color_1",
                "ui_speech_color_2",
                "ui_nameplate_color_1",
                "ui_nameplate_color_2",
            ]

            color_vars = {}

            color_frame = tk.LabelFrame(detail, text="Colors")
            color_frame.pack(fill="x", pady=5)

            for col in color_columns:
                row_color = tk.Frame(color_frame)
                row_color.pack(fill="x", pady=2)

                tk.Label(row_color, text=col, width=25, anchor="w").pack(side="left")

                current_hex = row[col_index[col]]

                if not current_hex:
                    current_hex = "#FFFFFF"
                else:
                    current_hex = current_hex.strip().replace("#", "")

                    # ensure valid hex length
                    if len(current_hex) < 6:
                        current_hex = current_hex.zfill(6)

                    # keep only first 6 if somehow longer
                    current_hex = current_hex[:6]

                    current_hex = "#" + current_hex.upper()

                var = tk.StringVar(value=current_hex)

                btn = tk.Button(row_color, width=4, bg=current_hex)

                def pick_color(v=var, b=btn):
                    chosen = colorchooser.askcolor(color=v.get())
                    if chosen[1]:
                        v.set(chosen[1])
                        b.config(bg=chosen[1])

                btn.config(command=pick_color)
                btn.pack(side="left", padx=5)

                color_vars[col] = var

            # ---------------- RANDOM TIME FIELDS ---------------- #

            time_columns = [
                "scale",
                "ear_random_time_min",
                "ear_random_time_max",
                "tail_random_time_min",
                "tail_random_time_max",
                "story_ear_random_time_min",
                "story_ear_random_time_max",
                "story_tail_random_time_min",
                "story_tail_random_time_max",
            ]

            time_vars = {}

            time_frame = tk.LabelFrame(detail, text="Parameter")
            time_frame.pack(fill="x", pady=5)

            for col in time_columns:
                row_time = tk.Frame(time_frame)
                row_time.pack(fill="x", pady=2)

                tk.Label(row_time, text=col, width=30, anchor="w").pack(side="left")

                var = tk.StringVar(value=str(row[col_index[col]]))
                tk.Entry(row_time, textvariable=var, width=10).pack(side="left")

                time_vars[col] = var

            chara_vars[cid] = (
                sex_var, height_var, shape_var, skin_var, bust_var,
                socks_var, race_var, eyebrow_var,
                tail_var, attach_var,
                color_vars, time_vars
            )

            # toggle logic
            def toggle(d=detail, b=header_btn):
                if d.winfo_ismapped():
                    d.pack_forget()
                    b.config(text=b.cget("text").replace("▼", "▶"))
                else:
                    d.pack(fill="x", padx=20, pady=5)
                    b.config(text=b.cget("text").replace("▶", "▼"))

            header_btn.config(command=toggle)

        conn.close()

        tk.Button(win, text="Save All", command=lambda: self.save_chara_expanded(chara_vars)).pack(pady=10)

    def save_chara_expanded(self, chara_vars):
        db_path = os.path.join(os.path.dirname(self.dat_path), "master", "master.mdb")
        conn = sqlite3.connect(db_path)
        c = conn.cursor()

        for cid, vars_tuple in chara_vars.items():

            (
                sex_var, height_var, shape_var, skin_var, bust_var,
                socks_var, race_var, eyebrow_var,
                tail_var, attach_var,
                color_vars, time_vars
            ) = vars_tuple

            # ---------------- DROPDOWNS ---------------- #

            sex_val = 1 if sex_var.get() == "Male" else 2
            height_val = int(height_var.get().split(" - ")[0])
            shape_val = int(shape_var.get().split(" - ")[0])
            skin_val = int(skin_var.get().split(" - ")[0])
            bust_val = int(bust_var.get().split(" - ")[0])
            socks_val = int(socks_var.get().split(" - ")[0])
            race_val = int(race_var.get().split(" - ")[0])
            eyebrow_val = int(eyebrow_var.get().split(" - ")[0])

            # ---------------- TAIL / ATTACHMENT ---------------- #

            # tail
            c.execute("SELECT tail_model_id FROM chara_data_bak WHERE id=?", (cid,))
            tail_backup = c.fetchone()[0]

            tail_model_val = tail_backup if tail_var.get() else -1

            # nail
            c.execute("SELECT attachment_model_id FROM chara_data_bak WHERE id=?", (cid,))
            attach_backup = c.fetchone()[0]

            attachment_val = attach_backup if attach_var.get() else -1

            # ---------------- UPDATE BASE FIELDS ---------------- #

            c.execute("""
                UPDATE chara_data
                SET sex=?, height=?, shape=?, skin=?, bust=?,
                    socks=?, race_running_type=?, mini_mayu_shader_type=?,
                    tail_model_id=?, attachment_model_id=?
                WHERE id=?
            """, (
                sex_val, height_val, shape_val, skin_val, bust_val,
                socks_val, race_val, eyebrow_val,
                tail_model_val, attachment_val,
                cid
            ))

            # ---------------- COLORS ---------------- #

            for col, var in color_vars.items():
                hex_value = var.get().replace("#", "").upper().zfill(6)

                c.execute(f"""
                    UPDATE chara_data
                    SET {col}=?
                    WHERE id=?
                """, (hex_value, cid))

            # ---------------- RANDOM TIMES ---------------- #

            for col, var in time_vars.items():
                try:
                    value = int(var.get())
                except:
                    value = 0

                c.execute(f"""
                    UPDATE chara_data
                    SET {col}=?
                    WHERE id=?
                """, (value, cid))

        conn.commit()
        conn.close()

        messagebox.showinfo("Success", "All character settings saved.")

    def preview_assets(self):
        preview_dir = os.path.join(self.mod_path.get(), "preview")
        if not os.path.isdir(preview_dir):
            messagebox.showerror("No Preview", "No 'preview' folder found in the selected mod.")
            return

        # Get images
        images = [f for f in os.listdir(preview_dir) if f.lower().endswith((".png", ".jpg", ".jpeg", ".bmp"))]
        if not images:
            messagebox.showinfo("No Images", "No preview images found.")
            return

        # Sort images by integer in filename
        def extract_number(filename):
            match = re.search(r'(\d+)', filename)
            return int(match.group(1)) if match else float('inf')

        images.sort(key=extract_number)

        # Open the first image with default program
        first_image_path = os.path.join(preview_dir, images[0])
        try:
            if sys.platform.startswith('darwin'):
                subprocess.call(('open', first_image_path))
            elif os.name == 'nt':  # Windows
                os.startfile(first_image_path)
            elif os.name == 'posix':
                subprocess.call(('xdg-open', first_image_path))
        except Exception as e:
            messagebox.showerror("Error", f"Failed to open image: {e}")


    def browse_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            self.mod_path.set(folder)
            self.reload()

    def reset_mod_info(self):
        self.title_text.set("")
        self.version_text.set("")
        self.description_box.configure(state="normal")
        self.description_box.delete("1.0", tk.END)
        self.description_box.configure(state="disabled")
        self.assets_load_btn.config(state="disabled")
        #self.assets_unload_btn.config(state="disabled")

    def reload(self):
        mod_folder = self.mod_path.get()

        json_path = os.path.join(mod_folder, "setting.json")
        yml_path = os.path.join(mod_folder, "setting.yml")

        data = None

        # --- try JSON first ---
        if os.path.isfile(json_path):
            try:
                with open(json_path, encoding="utf-8") as f:
                    data = json.load(f)
            except Exception as e:
                messagebox.showerror("Error", f"Failed to load setting.json:\n{e}")
                self.reset_mod_info()
                return

        # --- fallback to YAML ---
        elif os.path.isfile(yml_path):
            try:
                with open(yml_path, encoding="utf-8") as f:
                    data = yaml.safe_load(f)
            except Exception as e:
                messagebox.showerror("Error", f"Failed to load setting.yml:\n{e}")
                self.reset_mod_info()
                return

        # --- no config found ---
        else:
            messagebox.showerror("Error", "No setting.json or setting.yml found.")
            self.reset_mod_info()
            return

        self.title_text.set(data.get("title", "N/A"))
        self.version_text.set(f"mod_version: {data.get('mod_version', 'N/A')}")

        self.description_box.configure(state="normal")
        self.description_box.delete("1.0", tk.END)
        desc = data.get("description", [])
        if isinstance(desc, list):
            self.description_box.insert(tk.END, "\n".join(desc))
        else:
            self.description_box.insert(tk.END, str(desc))
        if data.get("modloader_version") != modloader_version:
            self.description_box.insert(tk.END, f"\n\n[Note] This mod was made for version {data['modloader_version']}")
        self.description_box.configure(state="disabled")

        mod_folder = self.mod_path.get()
        assets_exist = os.path.isdir(os.path.join(mod_folder, "assets"))

        self.assets_load_btn.config(state="normal" if assets_exist else "disabled")
        #self.assets_unload_btn.config(state="normal" if assets_exist else "disabled")

    def load_assets_manual(self):
        path = filedialog.askdirectory(title="Select Asset Folder")
        if not path:
            return

        has_pcs = messagebox.askyesnocancel(
            "Ask",
            "Does the mod contain Unencrypted PC assets (PC-s)?"
        )

        if has_pcs is None:
            return

        if has_pcs:
            mode = "decrypt"
            filter_folder = "PC-s"
        else:
            is_mod_encrypted = messagebox.askyesnocancel(
                "Ask",
                "Are these assets already encrypted / made for engine update?"
            )

            if is_mod_encrypted is None:
                return

            if is_mod_encrypted:
                mode = "direct"
            else:
                mode = "decrypt"
                filter_folder = "DMM"
                        
        # ---------------- LOAD ---------------- if is_mod_encrypted is true
        confirm = messagebox.askyesno(
            "Confirm",
            f"Load assets now?"
        )

        if not confirm:
            return
            
        if mode == "direct":
            rel_paths = self.scan_full_path(path)
            assets = [os.path.join(path, p) for p in rel_paths]

            if not assets:
                messagebox.showinfo("uhh", "there nothing inside.")
                return
                
            os.makedirs(self.backup_path, exist_ok=True)

            self.progress_bar["maximum"] = len(assets)
            self.progress_bar["value"] = 0

            loaded_count = 0
            missing_count = 0

            for i, src in enumerate(assets, start=1):
                filename = os.path.basename(src)

                # optional filter
                if len(filename) < 32:
                    continue

                dst = os.path.join(self.dat_path, filename[:2], filename)
                backup = os.path.join(self.backup_path, filename[:2], filename)

                if os.path.isfile(dst):
                    if not os.path.isfile(backup):
                        os.makedirs(os.path.dirname(backup), exist_ok=True)
                        shutil.move(dst, backup)
                    else:
                        os.remove(dst)
                else:
                    missing_count += 1
                    continue

                try:
                    shutil.copy(src, dst)
                    loaded_count += 1
                except Exception:
                    missing_count += 1
                    continue

                self.progress_label.config(text=f"Loading Asset {i} / {len(assets)}")
                self.progress_bar["value"] = i
                self.root.update_idletasks()

            self.progress_label.config(text="Waiting")

            messagebox.showinfo(
                "Success",
                f"{loaded_count} assets loaded successfully.\n"
                f"{missing_count} assets missing in dat folder."
            )
            return
        # ---------------- LOAD ---------------- if is_mod_encrypted is false
        elif mode == "decrypt":
            asset_folder = os.path.join(path, ".assets_cache")
            try:
                decoded_count, missing_meta = self.decrypt_assets_internal(path, asset_folder, use_hash=False, filter_path=filter_folder)
            except Exception as e:
                messagebox.showerror(
                    "Decrypt Error",
                    "Failed to decrypt assets.\n"
                    "This mod may be incompatible with the current game version or region.\n\n"
                    f"{e}"
                )
                return

            if not os.listdir(asset_folder):
                messagebox.showinfo("uhh", "there nothing inside.")
                shutil.rmtree(asset_folder, ignore_errors=True)
                return
                
            # --- Step 2: load assets from decrypted cache ---
            if not os.path.isdir(asset_folder):
                messagebox.showerror("Error", f"Asset cache not found: {asset_folder}")
                return

            os.makedirs(self.backup_path, exist_ok=True)
            assets = os.listdir(asset_folder)

            self.progress_bar["maximum"] = len(assets)
            self.progress_bar["value"] = 0

            for i, asset in enumerate(assets, start=1):
                src = os.path.join(asset_folder, asset)
                dst = os.path.join(self.dat_path, asset[:2], asset)
                backup = os.path.join(self.backup_path, asset[:2], asset)

                if os.path.isfile(dst):
                    if not os.path.isfile(backup):
                        os.makedirs(os.path.dirname(backup), exist_ok=True)
                        shutil.move(dst, backup)  # backup only once
                    else:
                        os.remove(dst)
                else:
                    messagebox.showerror(
                        "Error",
                        "Missing target file in dat folder.\nRun Uma Musume once with full data download first."
                    )
                    # cleanup cache before returning
                    if os.path.exists(asset_folder):
                        shutil.rmtree(asset_folder, ignore_errors=True)
                    return

                shutil.copy(src, dst)
                self.progress_label.config(text=f"Loading Asset {i} / {len(assets)}")
                self.progress_bar["value"] = i
                self.root.update_idletasks()

            # --- Step 3: cleanup ---
            if os.path.exists(asset_folder):
                shutil.rmtree(asset_folder, ignore_errors=True)
            self.progress_label.config(text="Waiting")
            messagebox.showinfo(
                "Success",
                f"{decoded_count} assets loaded successfully.\n"
                f"{missing_meta} assets were not found in meta database."
            )
            return

    def load_assets(self):
        folder = self.mod_path.get()
        if not folder or not os.path.isdir(folder):
            messagebox.showerror("Error", "Please select a valid mod folder first.")
            return
        asset_folder_v = os.path.join(folder, "assets")
        asset_folder = os.path.join(folder, "assets_cache")
        try:
            decoded_count, missing_meta = self.decrypt_assets_internal(asset_folder_v, asset_folder, use_hash=False, filter_path=None)
        except Exception as e:
            messagebox.showerror(
                "Decrypt Error",
                "Failed to decrypt assets.\n"
                "This mod may be incompatible with the current game version or region.\n\n"
                f"{e}"
            )
            return

        if not os.listdir(asset_folder):
            messagebox.showinfo("uhh", "there nothing inside.")
            shutil.rmtree(asset_folder, ignore_errors=True)
            return
            
        # --- Step 2: load assets from decrypted cache ---
        if not os.path.isdir(asset_folder):
            messagebox.showerror("Error", f"Asset cache not found: {asset_folder}")
            return

        os.makedirs(self.backup_path, exist_ok=True)
        assets = os.listdir(asset_folder)

        self.progress_bar["maximum"] = len(assets)
        self.progress_bar["value"] = 0

        for i, asset in enumerate(assets, start=1):
            src = os.path.join(asset_folder, asset)
            dst = os.path.join(self.dat_path, asset[:2], asset)
            backup = os.path.join(self.backup_path, asset[:2], asset)

            if os.path.isfile(dst):
                if not os.path.isfile(backup):
                    os.makedirs(os.path.dirname(backup), exist_ok=True)
                    shutil.move(dst, backup)  # backup only once
                else:
                    os.remove(dst)
            else:
                messagebox.showerror(
                    "Error",
                    "Missing target file in dat folder.\nRun Uma Musume once with full data download first."
                )
                # cleanup cache before returning
                if os.path.exists(asset_folder):
                    shutil.rmtree(asset_folder, ignore_errors=True)
                return

            shutil.copy(src, dst)
            self.progress_label.config(text=f"Loading Asset {i} / {len(assets)}")
            self.progress_bar["value"] = i
            self.root.update_idletasks()

        # --- Step 3: cleanup ---
        if os.path.exists(asset_folder):
            shutil.rmtree(asset_folder, ignore_errors=True)
        self.progress_label.config(text="Waiting")
        messagebox.showinfo(
            "Success",
            f"{decoded_count} assets loaded successfully.\n"
            f"{missing_meta} assets were not found in meta database."
        )

    def unload_assets(self):
        folder = self.mod_path.get()
        asset_folder = os.path.join(folder, "assets")

        self.progress_bar["maximum"] = len(assets)
        self.progress_bar["value"] = 0

        for i, asset in enumerate(assets, start=1):
            dst = os.path.join(self.dat_path, asset[:2], asset)
            backup = os.path.join(self.backup_path, asset[:2], asset)

            if os.path.isfile(backup):
                if os.path.exists(dst):
                    os.remove(dst)
                shutil.move(backup, dst)

            self.progress_label.config(text=f"Unloading Asset {i} / {len(assets)}")
            self.progress_bar["value"] = i
            self.root.update_idletasks()
        messagebox.showinfo("Success", "Assets unloaded successfully.")
        self.progress_label.config(text="Waiting")

    def restore_original_assets(self):
        # collect backup files
        backup_files = []
        for root_dir, dirs, files in os.walk(self.backup_path):
            for file in files:
                rel_path = os.path.relpath(os.path.join(root_dir, file), self.backup_path)
                backup_files.append(rel_path)

        if not backup_files:
            messagebox.showinfo("Info", "No backup files found.")
            return

        # lookup friendly names from meta db
        meta_path = self.meta_path
        name_map = {}
        if os.path.isfile(meta_path):
            try:
                hashes = [os.path.basename(f) for f in backup_files]
                name_map = {}

                if hashes:
                    try:
                        conn = sqlite3.connect(meta_path)
                        c = conn.cursor()

                        # SQLite has limit (~999), so chunk it
                        chunk_size = 900
                        for i in range(0, len(hashes), chunk_size):
                            chunk = hashes[i:i + chunk_size]
                            placeholders = ",".join(["?"] * len(chunk))

                            c.execute(f"SELECT h, n FROM a WHERE h IN ({placeholders})", chunk)

                            for h, n in c.fetchall():
                                name_map[h] = n

                        conn.close()

                    except Exception as e:
                        messagebox.showwarning("Meta DB", f"Failed batch lookup:\n{e}")
                conn.close()
            except Exception as e:
                messagebox.showwarning("Meta DB", f"Failed to read meta database:\n{e}")

        # create window
        win = tk.Toplevel(self.root)
        win.title("Restore Original Assets")
        win.geometry("800x500")

        frame = tk.Frame(win)
        frame.pack(fill="both", expand=True)

        scrollbar = tk.Scrollbar(frame)
        scrollbar.pack(side="right", fill="y")

        listbox = tk.Listbox(frame, selectmode="extended", yscrollcommand=scrollbar.set, width=100, height=20)
        entries = [
            (f, name_map.get(os.path.basename(f), os.path.basename(f)))
            for f in backup_files
        ]
        entries.sort(key=lambda x: x[1].lower())  # sort by friendly name
        listbox.insert(tk.END, *[display_name for _, display_name in entries])
        listbox.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=listbox.yview)

        def restore_selected():
            sel = listbox.curselection()
            if not sel:
                messagebox.showinfo("Info", "No files selected.")
                return

            if not messagebox.askyesno("Confirm", f"Restore {len(sel)} selected file(s)?"):
                return

            restored = 0
            for idx in sel:
                rel_path = entries[idx][0]
                backup_file = os.path.join(self.backup_path, rel_path)
                dat_file = os.path.join(self.dat_path, rel_path)
                os.makedirs(os.path.dirname(dat_file), exist_ok=True)
                if os.path.exists(dat_file):
                    os.remove(dat_file)
                shutil.move(backup_file, dat_file)
                restored += 1
            messagebox.showinfo("Done", f"Restored {restored} selected file(s).")

        def restore_all():
            if not messagebox.askyesno("Confirm", "Restore all original assets? This will overwrite all modified files."):
                return

            restored = 0
            for rel_path, _ in entries:
                backup_file = os.path.join(self.backup_path, rel_path)
                dat_file = os.path.join(self.dat_path, rel_path)
                os.makedirs(os.path.dirname(dat_file), exist_ok=True)
                if os.path.exists(dat_file):
                    os.remove(dat_file)
                shutil.move(backup_file, dat_file)
                restored += 1
            messagebox.showinfo("Done", f"Restored {restored} file(s).")

        btn_frame = tk.Frame(win)
        btn_frame.pack(pady=10)
        tk.Button(btn_frame, text="Restore Selected", command=restore_selected).pack(side="left", padx=5)
        tk.Button(btn_frame, text="Restore All", command=restore_all).pack(side="left", padx=5)


    def delete_master_db(self):
        db_path = os.path.join(os.path.dirname(self.dat_path), "master", "master.mdb")
        if not os.path.isfile(db_path):
            messagebox.showinfo("Info", "master.mdb not found, nothing to delete.")
            return

        if not messagebox.askyesno(
            "Confirm Delete",
            "This will delete master.mdb.\n\n"
            "The game will download a fresh copy after login.\n\n"
            "Are you sure you want to continue?"
        ):
            return

        try:
            os.remove(db_path)
            messagebox.showinfo("Deleted", "master.mdb deleted successfully.\nRe-login to download a new database.")
        except Exception as e:
            messagebox.showerror("Error", f"Could not delete database:\n{e}")

        return exists

if __name__ == "__main__":
    root = tk.Tk()
    app = ModLoaderGUI(root)
    root.mainloop()
