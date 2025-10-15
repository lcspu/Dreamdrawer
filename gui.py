# 项目数字 22
import sys, os, threading, websocket, json, time, argparse, builtins
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QTabWidget, QGroupBox, QLabel, QLineEdit, QPushButton, QCheckBox, QProgressBar, QTextEdit, QFileDialog, QMessageBox, QFrame, QScrollArea, QGridLayout, QSizePolicy)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QSize
from PyQt5.QtGui import QFont, QPalette, QColor, QTextCursor, QFontDatabase, QPixmap, QIcon
from PIL import Image

QUADRANT_MAP = {
    (1, 1, 1, 1): '█', (0, 0, 0, 0): ' ',
    (1, 0, 0, 0): '▘', (0, 1, 0, 0): '▝',
    (0, 0, 1, 0): '▖', (0, 0, 0, 1): '▗',
    (1, 1, 0, 0): '▀', (0, 0, 1, 1): '▄',
    (1, 0, 1, 0): '▌', (0, 1, 0, 1): '▐',
    (1, 0, 1, 1): '▙', (0, 1, 1, 1): '▟',
    (1, 1, 1, 0): '▛', (1, 1, 0, 1): '▜',
    (1, 0, 0, 1): '▚', (0, 1, 1, 0): '▞'
}
SQUARE_WIDTH = 16
SQUARE_HEIGHT = 8

deployment_active = False
current_ws_connections = []
global_log_function = None

# Custom print function that redirects to GUI log
def print(*args, **kwargs):
    message = ' '.join(str(arg) for arg in args)
    if global_log_function:
        global_log_function(message)
    else:
        # Fallback to regular print if GUI not available 
        builtins.print(message, **kwargs)

# Get absolute path to resource
def resource_path(relative_path):
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

def resize_image(input_path, output_path):
    try:
        with Image.open(input_path) as img:
            original_width, original_height = img.size
            new_width = int(original_width * 1.20)  # +20% width
            new_height = int(original_height * 0.70)  # -30% height
            resized_img = img.resize((new_width, new_height), Image.LANCZOS)
            resized_img.save(output_path)
            print(f"[!] New image resize saved to: {output_path}")
            return True
    except Exception as e:
        print(f"[X] Error resizing image: {e}")
        return False

def prepare_image_for_mode(image_file):
    if not os.path.exists(image_file):
        print(f"[X] Image file not found: {image_file}")
        return None
    
    # Check if file already has '_resized' in name
    base_name = os.path.basename(image_file)
    if '_resized' in base_name:
        print(f"[!] Using already resized image: {image_file}")
        return image_file
    
    # Create resized version
    base, ext = os.path.splitext(image_file)
    output_image = f"{base}_resized{ext}"
    
    if os.path.exists(output_image):
        print(f"[!] Resized image already exists: {output_image}")
        return output_image
    
    print(f"[!] Resizing image: {image_file}")
    if resize_image(image_file, output_image):
        return output_image
    else:
        print(f"[!] Using original image without resizing: {image_file}")
        return image_file

def parse_proxy_file(filename):
    proxies = []
    try:
        with open(filename, 'r') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                
                # Remove protocol prefix if present
                if line.startswith('http://'):
                    line = line[7:]
                elif line.startswith('socks5://'):
                    line = line[9:]
                elif line.startswith('socks4://'):
                    line = line[9:]
                
                parts = line.split(':')
                
                if len(parts) >= 2:
                    host = parts[0].strip()
                    try:
                        port = int(parts[1].strip())
                        proxy = {"host": host, "port": port}
                        
                        # Add auth if provided
                        if len(parts) >= 4:
                            proxy["auth"] = f"{parts[2].strip()}:{parts[3].strip()}"
                        
                        proxies.append(proxy)
                    except ValueError:
                        print(f"[X] Invalid port in line {line_num}: {line}")
                else:
                    print(f"[X] Invalid format in line {line_num}: {line}")
                    
    except FileNotFoundError:
        print(f"[X] Proxy file not found: {filename}")
        return []
    except Exception as e:
        print(f"[X] Error reading proxy file: {e}")
        return []
    
    print(f"[!] Loaded {len(proxies)} proxies from {filename}")
    return proxies

def brightness(rgb):
    r, g, b = rgb
    return 0.299 * r + 0.587 * g + 0.114 * b

def choose_quadrant(pixels):
    avg_brightness = sum(brightness(p) for p in pixels) / 4
    return tuple(1 if brightness(p) < avg_brightness else 0 for p in pixels)

def average_color(pixels):
    r = sum(p[0] for p in pixels) // len(pixels)
    g = sum(p[1] for p in pixels) // len(pixels)
    b = sum(p[2] for p in pixels) // len(pixels)
    return (r, g, b)

def stop_all_deployments():
    global deployment_active, current_ws_connections
    deployment_active = False
    for ws in current_ws_connections:
        try:
            ws.close()
        except:
            pass
    current_ws_connections.clear()

# ==== ASCII SINGLE MODE ====
def ascii_single_mode(args):
    global deployment_active, current_ws_connections
    print("\n=== ASCII Single Mode ===")
    
    if not os.path.exists(args.ascii_file):
        print(f"Error: File not found: {args.ascii_file}")
        return
    
    with open(args.ascii_file, 'r', encoding='utf-8') as f:
        ascii_lines = [line.rstrip('\n') for line in f]

    all_edits = []
    word_count = 0
    for row_index, line in enumerate(ascii_lines):
        for col_index, char in enumerate(line):
            x = args.start_x * 16 + col_index
            y = args.start_y * 8 + row_index
            block_x = x // 16
            block_y = y // 8
            part_x = x % 16
            part_y = y % 8
            
            timestamp = int(time.time())
            color = int(args.color.lstrip("#"), 16) if args.color else int("#000000".lstrip("#"), 16)
            bg_color = int(args.bg_color.lstrip("#"), 16) if args.bg_color else None
            
            if args.wipe == "on":edit = [block_y, block_x, part_y, part_x, timestamp, " ", word_count, color]
            else:edit = [block_y, block_x, part_y, part_x, timestamp, char, word_count, color] + ([bg_color] if bg_color is not None else [])
            all_edits.append(edit)
            word_count += 1

    deployment_active = True
    current_ws = None

    def on_open(ws):
        nonlocal current_ws
        current_ws = ws
        current_ws_connections.append(ws)
        if args.repeat == float('inf'):
            repetition_count = 0
            while deployment_active:
                repetition_count += 1
                print(f"[!] Repetition {repetition_count} (infinite mode)")
                for i in range(0, len(all_edits), args.chunk_size):
                    if not deployment_active:
                        break
                    chunk = all_edits[i:i + args.chunk_size]
                    payload = {"kind": "write", "edits": chunk}
                    ws.send(json.dumps(payload))
                    print(f"Sent chunk {i // args.chunk_size + 1}")
                    time.sleep(args.sleep_between)
                if not deployment_active:
                    break
        else:
            for repeat in range(args.repeat):
                if not deployment_active:
                    break
                print(f"[!] Repetition {repeat + 1}/{args.repeat}")
                for i in range(0, len(all_edits), args.chunk_size):
                    if not deployment_active:
                        break
                    chunk = all_edits[i:i + args.chunk_size]
                    payload = {"kind": "write", "edits": chunk}
                    ws.send(json.dumps(payload))
                    print(f"Sent chunk {i // args.chunk_size + 1}")
                    time.sleep(args.sleep_between)
                if not deployment_active:
                    break
        ws.close()
        if ws in current_ws_connections:
            current_ws_connections.remove(ws)

    def on_error(ws, error):
        pass
        # print("Error:", error)

    def on_close(ws, code, msg):
        print("Connection closed.")
        if ws in current_ws_connections:
            current_ws_connections.remove(ws)

    ws_app = websocket.WebSocketApp(
        args.server_url,
        on_open=on_open,
        on_error=on_error,
        on_close=on_close
    )

    if args.proxy_host and args.proxy_port:
        print(f"Using proxy: {args.proxy_host}:{args.proxy_port}")
        ws_app.run_forever(
            http_proxy_host=args.proxy_host,
            http_proxy_port=args.proxy_port,
            proxy_type="http"
        )
    else:
        print("Using direct connection (no proxy)")
        ws_app.run_forever()

# ==== ASCII THREADING MODE ====
def ascii_threading_mode(args):
    global deployment_active, current_ws_connections
    print("\n=== ASCII Threading Mode ===")
    
    if not os.path.exists(args.ascii_file):
        print(f"Error: File not found: {args.ascii_file}")
        return
    
    # Parse proxies from file
    if not args.proxies:
        print("No proxies provided for threading mode!")
        return
    
    with open(args.ascii_file, 'r', encoding='utf-8') as f:
        ascii_lines = [line.rstrip('\n') for line in f]
    total_rows = len(ascii_lines)

    def prepare_edits(lines_subset, offset_rows):
        edits = []
        word_count = 0
        for row_index, line in enumerate(lines_subset):
            for col_index, char in enumerate(line):
                x = args.start_x * 16 + col_index
                y = args.start_y * 8 + (row_index + offset_rows)
                block_x = x // 16
                block_y = y // 8
                part_x = x % 16
                part_y = y % 8
                
                timestamp = int(time.time())
                color = int(args.color.lstrip("#"), 16) if args.color else int("#000000".lstrip("#"), 16)
                bg_color = int(args.bg_color.lstrip("#"), 16) if args.bg_color else None
                
                if args.wipe == "on":edit = [block_y, block_x, part_y, part_x, timestamp, " ", word_count, color]
                else:edit = [block_y, block_x, part_y, part_x, timestamp, char, word_count, color] + ([bg_color] if bg_color is not None else [])
                edits.append(edit)
                word_count += 1
        return edits

    def send_edits(proxy, edits):
        if not deployment_active:
            return
            
        current_ws = None

        def on_open(ws):
            nonlocal current_ws
            current_ws = ws
            current_ws_connections.append(ws)
            if args.repeat == float('inf'):
                repetition_count = 0
                while deployment_active:
                    repetition_count += 1
                    print(f"[{proxy['host']}:{proxy['port']}] [!] Repetition {repetition_count} (infinite mode)")
                    for i in range(0, len(edits), args.chunk_size):
                        if not deployment_active:
                            break
                        chunk = edits[i:i + args.chunk_size]
                        payload = {"kind": "write", "edits": chunk}
                        ws.send(json.dumps(payload))
                        print(f"[{proxy['host']}:{proxy['port']}] Sent chunk {i // args.chunk_size + 1}")
                        time.sleep(args.sleep_between)
                    if not deployment_active:
                        break
            else:
                for repeat in range(args.repeat):
                    if not deployment_active:
                        break
                    print(f"[{proxy['host']}:{proxy['port']}] [!] Repetition {repeat + 1}/{args.repeat}")
                    for i in range(0, len(edits), args.chunk_size):
                        if not deployment_active:
                            break
                        chunk = edits[i:i + args.chunk_size]
                        payload = {"kind": "write", "edits": chunk}
                        ws.send(json.dumps(payload))
                        print(f"[{proxy['host']}:{proxy['port']}] Sent chunk {i // args.chunk_size + 1}")
                        time.sleep(args.sleep_between)
                    if not deployment_active:
                        break
            ws.close()
            if ws in current_ws_connections:
                current_ws_connections.remove(ws)

        def on_error(ws, error):
            pass
            # print(f"[{proxy['host']}:{proxy['port']}] Error:", error)

        def on_close(ws, code, msg):
            print(f"[{proxy['host']}:{proxy['port']}] Connection closed.")
            if ws in current_ws_connections:
                current_ws_connections.remove(ws)

        ws_app = websocket.WebSocketApp(
            args.server_url,
            on_open=on_open,
            on_error=on_error,
            on_close=on_close
        )

        ws_app.run_forever(
            http_proxy_host=proxy["host"],
            http_proxy_port=proxy["port"],
            proxy_type="http"
        )

    deployment_active = True
    rows_per_proxy = total_rows // len(args.proxies)
    threads = []
    for i, proxy in enumerate(args.proxies):
        start_row = i * rows_per_proxy
        if i == len(args.proxies) - 1:
            end_row = total_rows
        else:
            end_row = (i + 1) * rows_per_proxy
        lines_subset = ascii_lines[start_row:end_row]
        offset_rows = start_row
        edits = prepare_edits(lines_subset, offset_rows)
        t = threading.Thread(target=send_edits, args=(proxy, edits))
        t.daemon = True
        t.start()
        threads.append(t)
    
    for t in threads:
        t.join()
    print("[!] All proxies finished sending.")

# ==== IMAGE SINGLE MODE ====
def image_single_mode(args):
    global deployment_active, current_ws_connections
    
    print("\n=== Image Single Mode ===")
    
    # Prepare image (resize if needed)
    processed_image = prepare_image_for_mode(args.image_file)
    if not processed_image:
        return
    
    img = Image.open(processed_image).convert("RGB")
    width, height = img.size
    pixels = img.load()

    edits = []
    word_count = 0
    for y in range(height):
        for x in range(width):
            r, g, b = pixels[x, y]
            hex_color0 = f"#{r:02x}{g:02x}{b:02x}"
            hex_color = int(hex_color0.lstrip("#"), 16)

            abs_x = args.start_x * SQUARE_WIDTH + x
            abs_y = args.start_y * SQUARE_HEIGHT + y

            block_x = abs_x // SQUARE_WIDTH
            block_y = abs_y // SQUARE_HEIGHT
            part_x = abs_x % SQUARE_WIDTH
            part_y = abs_y % SQUARE_HEIGHT

            if args.wipe == "on":edit = [block_y, block_x, part_y, part_x, int(time.time()), " ", word_count, 0]
            else:edit = [block_y, block_x, part_y, part_x, int(time.time()), " ", word_count, 0, hex_color]
            edits.append(edit)
            word_count += 1

    deployment_active = True
    current_ws = None

    def on_open(ws):
        nonlocal current_ws
        current_ws = ws
        current_ws_connections.append(ws)
        if args.repeat == float('inf'):
            repetition_count = 0
            while deployment_active:
                repetition_count += 1
                print(f"[!] Repetition {repetition_count} (infinite mode)")
                for i in range(0, len(edits), args.chunk_size):
                    if not deployment_active:
                        break
                    chunk = edits[i:i + args.chunk_size]
                    payload = {"kind": "write", "edits": chunk}
                    ws.send(json.dumps(payload))
                    print(f"Chunk {i // args.chunk_size + 1} sent.")
                    time.sleep(args.sleep_between)
                if not deployment_active:
                    break
        else:
            for repeat in range(args.repeat):
                if not deployment_active:
                    break
                print(f"[!] Repetition {repeat + 1}/{args.repeat}")
                for i in range(0, len(edits), args.chunk_size):
                    if not deployment_active:
                        break
                    chunk = edits[i:i + args.chunk_size]
                    payload = {"kind": "write", "edits": chunk}
                    ws.send(json.dumps(payload))
                    print(f"Chunk {i // args.chunk_size + 1} sent.")
                    time.sleep(args.sleep_between)
                if not deployment_active:
                    break
        ws.close()
        if ws in current_ws_connections:
            current_ws_connections.remove(ws)

    def on_error(ws, error):
        pass
        # print("WebSocket error:", error)

    def on_close(ws, code, msg):
        print("Connection closed.")
        if ws in current_ws_connections:
            current_ws_connections.remove(ws)

    ws_app = websocket.WebSocketApp(
        args.server_url,
        on_open=on_open,
        on_error=on_error,
        on_close=on_close
    )

    if args.proxy_host and args.proxy_port:
        print(f"Using proxy: {args.proxy_host}:{args.proxy_port}")
        ws_app.run_forever(
            http_proxy_host=args.proxy_host,
            http_proxy_port=args.proxy_port,
            proxy_type="http"
        )
    else:
        print("Using direct connection (no proxy)")
        ws_app.run_forever()

# ==== IMAGE THREADING MODE ====
def image_threading_mode(args):
    global deployment_active, current_ws_connections
    
    print("\n=== Image Threading Mode ===")
    
    # Prepare image (resize if needed)
    processed_image = prepare_image_for_mode(args.image_file)
    if not processed_image:
        return

    # Parse proxies from file
    if not args.proxies:
        print("No proxies provided for threading mode!")
        return
    
    def send_region(proxy, img_part, offset_y_tiles):
        if not deployment_active:
            return
            
        pixels = img_part.load()
        edits = []
        word_count = 0
        width, height = img_part.size

        for y in range(0, height, 2):
            for x in range(0, width, 2):
                try:
                    p1 = pixels[x, y]
                    p2 = pixels[x + 1, y]
                    p3 = pixels[x, y + 1]
                    p4 = pixels[x + 1, y + 1]

                    block = [p1, p2, p3, p4]
                    quadrant = choose_quadrant(block)
                    character = QUADRANT_MAP.get(quadrant, '█')

                    dark_pixels = [block[i] for i in range(4) if quadrant[i] == 1]
                    light_pixels = [block[i] for i in range(4) if quadrant[i] == 0]

                    if not dark_pixels: dark_pixels = block
                    if not light_pixels: light_pixels = block

                    character_color = average_color(dark_pixels)
                    background_color = average_color(light_pixels)

                    hex_char_color = int(f"{character_color[0]:02x}{character_color[1]:02x}{character_color[2]:02x}", 16)
                    hex_bg_color = int(f"{background_color[0]:02x}{background_color[1]:02x}{background_color[2]:02x}", 16)

                    abs_x = args.start_x * SQUARE_WIDTH + (x // 2)
                    abs_y = args.start_y * SQUARE_HEIGHT + offset_y_tiles + (y // 2)

                    block_x = abs_x // SQUARE_WIDTH
                    block_y = abs_y // SQUARE_HEIGHT
                    part_x = abs_x % SQUARE_WIDTH
                    part_y = abs_y % SQUARE_HEIGHT

                    if args.wipe == "on":edits.append([block_y, block_x, part_y, part_x, int(time.time()), " ", word_count, 0])
                    else:edits.append([block_y, block_x, part_y, part_x, int(time.time()), character, word_count, hex_char_color, hex_bg_color])
                    word_count += 1
                except IndexError:
                    continue

        current_ws = None

        def on_open(ws):
            nonlocal current_ws
            current_ws = ws
            current_ws_connections.append(ws)
            if args.repeat == float('inf'):
                repetition_count = 0
                while deployment_active:
                    repetition_count += 1
                    print(f"[{proxy['host']}:{proxy['port']}] [!] Repetition {repetition_count} (infinite mode)")
                    for i in range(0, len(edits), args.chunk_size):
                        if not deployment_active:
                            break
                        chunk = edits[i:i + args.chunk_size]
                        payload = {"kind": "write", "edits": chunk}
                        ws.send(json.dumps(payload))
                        print(f"[{proxy['host']}:{proxy['port']}] Sent chunk {i // args.chunk_size + 1}")
                        time.sleep(args.sleep_between)
                    if not deployment_active:
                        break
            else:
                for repeat in range(args.repeat):
                    if not deployment_active:
                        break
                    print(f"[{proxy['host']}:{proxy['port']}] [!] Repetition {repeat + 1}/{args.repeat}")
                    for i in range(0, len(edits), args.chunk_size):
                        if not deployment_active:
                            break
                        chunk = edits[i:i + args.chunk_size]
                        payload = {"kind": "write", "edits": chunk}
                        ws.send(json.dumps(payload))
                        print(f"[{proxy['host']}:{proxy['port']}] Sent chunk {i // args.chunk_size + 1}")
                        time.sleep(args.sleep_between)
                    if not deployment_active:
                        break
            ws.close()
            if ws in current_ws_connections:
                current_ws_connections.remove(ws)

        def on_error(ws, error):
            pass
            # print(f"[{proxy['host']}:{proxy['port']}] WebSocket error:", error)

        def on_close(ws, code, msg):
            print(f"[{proxy['host']}:{proxy['port']}] Connection closed.")
            if ws in current_ws_connections:
                current_ws_connections.remove(ws)

        ws_app = websocket.WebSocketApp(
            args.server_url,
            on_open=on_open,
            on_error=on_error,
            on_close=on_close
        )

        ws_app.run_forever(
            http_proxy_host=proxy["host"],
            http_proxy_port=proxy["port"],
            proxy_type="http"
        )

    deployment_active = True
    img = Image.open(processed_image).convert("RGB")
    width, height = img.size
    
    if width % 2 != 0: width -= 1
    if height % 2 != 0: height -= 1
    img = img.crop((0, 0, width, height))
    
    if height < 80:
        proxies_to_use = args.proxies[:2]
    else:
        proxies_to_use = args.proxies
        
    part_height = height // len(proxies_to_use)
    threads = []
    for i, proxy in enumerate(proxies_to_use):
        y_start = i * part_height
        y_end = (i + 1) * part_height if i < len(proxies_to_use) - 1 else height
        if (y_end - y_start) % 2 != 0: y_end -= 1
        img_part = img.crop((0, y_start, width, y_end))
        offset_y_tiles = (y_start) // 2
        t = threading.Thread(target=send_region, args=(proxy, img_part, offset_y_tiles))
        t.daemon = True
        t.start()
        threads.append(t)
    
    for t in threads:
        t.join()
    print("[!] All proxies finished sending.")

class DeploymentThread(QThread):
    log_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int)
    finished_signal = pyqtSignal(bool)
    
    def __init__(self, args):
        super().__init__()
        self.args = args
        self.is_running = True
        
    def run(self):
        try:
            self.log_signal.emit(f"[INFO] Position: ({self.args.start_x}, {self.args.start_y})")
            if self.args.repeat == float('inf'):
                self.log_signal.emit(f"[INFO] Repetitions: Infinite")
            else:
                self.log_signal.emit(f"[INFO] Repetitions: {self.args.repeat}")
            self.log_signal.emit(f"[INFO] Chunk size: {self.args.chunk_size}")
            self.log_signal.emit(f"[INFO] Sleep: {self.args.sleep_between}s")
            self.log_signal.emit(f"[INFO] Wipe mode: {self.args.wipe}")
            if hasattr(self.args, 'color') and self.args.color:
                self.log_signal.emit(f"[INFO] Color: {self.args.color}")
            if hasattr(self.args, 'bg_color') and self.args.bg_color:
                self.log_signal.emit(f"[INFO] Background Color: {self.args.bg_color}")
            self.log_signal.emit("-" * 50)
            
            if self.args.mode == 'ascii_single':ascii_single_mode(self.args)
            elif self.args.mode == 'ascii_threading':ascii_threading_mode(self.args)
            elif self.args.mode == 'image_single':image_single_mode(self.args)
            elif self.args.mode == 'image_threading':image_threading_mode(self.args)
                
            self.log_signal.emit("[SUCCESS] Task completed successfully")
            self.finished_signal.emit(True)
            
        except Exception as e:
            self.log_signal.emit(f"[ERROR] Task failed: {str(e)}")
            self.finished_signal.emit(False)
            
    def stop(self):
        self.is_running = False
        stop_all_deployments()

class DreamaLineEdit(QLineEdit):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setMinimumHeight(20)
        self.setMaximumHeight(20)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setStyleSheet("""
            QLineEdit {
                background-color: #000000;
                color: #c0c0c0;
                border: 1px solid #404040;
                border-radius: 1px;
                padding: 1px 3px;
                font-family: 'Segoe UI';
                font-size: 7pt;
                selection-background-color: #005712;
            }
            QLineEdit:focus {
                border: 1px solid #005712;
            }
            QLineEdit:disabled {
                background-color: #1a1a1a;
                color: #666666;
            }
        """)

class DreamaButton(QPushButton):
    def __init__(self, text, *args, **kwargs):
        super().__init__(text, *args, **kwargs)
        self.setMinimumHeight(20)
        self.setMaximumHeight(20)
        self.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.setStyleSheet("""
            QPushButton {
                background-color: #2a2a2a;
                color: #c0c0c0;
                border: 1px solid #404040;
                border-radius: 1px;
                padding: 2px 6px;
                font-family: 'Segoe UI';
                font-size: 9pt;
                font-weight: normal;
                min-width: 50px;
            }
            QPushButton:hover {
                background-color: #3a3a3a;
                border: 1px solid #505050;
            }
            QPushButton:pressed {
                background-color: #1a1a1a;
                border: 1px solid #005712;
            }
            QPushButton:disabled {
                background-color: #1a1a1a;
                color: #666666;
                border: 1px solid #333333;
            }
            QPushButton:focus {
                border: 1px solid #005712;
            }
        """)

class DreamaCheckBox(QCheckBox):
    def __init__(self, text, *args, **kwargs):
        super().__init__(text, *args, **kwargs)
        self.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.setStyleSheet("""
            QCheckBox {
                color: #c0c0c0;
                font-family: 'Segoe UI';
                font-size: 8pt;
                spacing: 3px;
                background-color: transparent;
            }
            QCheckBox::indicator {
                width: 10px;
                height: 10px;
                border: 1px solid #404040;
                border-radius: 1px;
                background-color: #000000;
            }
            QCheckBox::indicator:checked {
                background-color: #005712;
                border: 1px solid #005712;
            }
            QCheckBox::indicator:hover {
                border: 1px solid #005712;
            }
            QCheckBox::indicator:disabled {
                background-color: #1a1a1a;
                border: 1px solid #333333;
            }
        """)

class DreamaTextEdit(QTextEdit):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setStyleSheet("""
            QTextEdit {
                background-color: #000000;
                color: #c0c0c0;
                border: 1px solid #404040;
                border-radius: 1px;
                font-family: 'Consolas';
                font-size: 8pt;
                padding: 2px;
                selection-background-color: #005712;
            }
        """)

class DreamaProgressBar(QProgressBar):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setStyleSheet("""
            QProgressBar {
                border: 1px solid #404040;
                border-radius: 1px;
                text-align: center;
                background-color: #000000;
                color: #c0c0c0;
                font-family: 'Segoe UI';
                font-size: 8pt;
                height: 16px;
            }
            QProgressBar::chunk {
                background-color: #005712;
                border-radius: 1px;
            }
        """)

class CompactTabWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(6, 6, 6, 6)
        self.layout.setSpacing(4)
        
    def add_group(self, title, widget):
        group = QGroupBox(title)
        group.setStyleSheet("""
            QGroupBox {
                color: #c0c0c0;
                font-family: 'Segoe UI';
                font-size: 8pt;
                font-weight: bold;
                border: 1px solid #404040;
                border-radius: 1px;
                margin-top: 6px;
                padding-top: 8px;
                background-color: #0a0a0a;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 5px;
                padding: 0 3px 0 3px;
                background-color: #0a0a0a;
            }
        """)
        group_layout = QVBoxLayout(group)
        group_layout.setContentsMargins(5, 8, 5, 5)
        group_layout.setSpacing(3)
        group_layout.addWidget(widget)
        self.layout.addWidget(group)
        
    def add_widget(self, widget):
        self.layout.addWidget(widget)

class HeaderImageLabel(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet("""
            QLabel {
                background-color: transparent;
                border: none;
            }
        """)
        
    def set_header_image(self, image_path):
        pixmap = QPixmap(image_path)
        # Scale image to fit 490x80 while maintaining aspect ratio
        scaled_pixmap = pixmap.scaled(490, 80, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.setPixmap(scaled_pixmap)
        self.setFixedSize(490, 80)
        return True

class PixelArtGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.deployment_thread = None
        self.server_url = "wss://ourworldoftext.com/ws/"
        global global_log_function
        global_log_function = self.log_message
        
        # Separate variables for each tab - FIXED: Added proper storage for all input fields
        self.ascii_file_edit = None
        self.ascii_threading_file_edit = None
        self.image_file_edit = None
        self.image_threading_file_edit = None
        
        self.wipe_checkbox_ascii_single = None
        self.wipe_checkbox_ascii_threading = None
        self.wipe_checkbox_image_single = None
        self.wipe_checkbox_image_threading = None
        
        # FIXED: Added storage for proxy file edit fields
        self.proxy_file_edit_ascii_threading = None
        self.proxy_file_edit_image_threading = None
        
        # FIXED: Added separate input fields for each tab
        self.x_edit_ascii_single = None
        self.y_edit_ascii_single = None
        self.repeat_edit_ascii_single = None
        self.chunk_edit_ascii_single = None
        self.sleep_edit_ascii_single = None
        
        self.x_edit_ascii_threading = None
        self.y_edit_ascii_threading = None
        self.repeat_edit_ascii_threading = None
        self.chunk_edit_ascii_threading = None
        self.sleep_edit_ascii_threading = None
        
        self.x_edit_image_single = None
        self.y_edit_image_single = None
        self.repeat_edit_image_single = None
        self.chunk_edit_image_single = None
        self.sleep_edit_image_single = None
        
        self.x_edit_image_threading = None
        self.y_edit_image_threading = None
        self.repeat_edit_image_threading = None
        self.chunk_edit_image_threading = None
        self.sleep_edit_image_threading = None
        
        # FIXED: Added proxy host/port for single modes
        self.host_edit_ascii_single = None
        self.port_edit_ascii_single = None
        self.host_edit_image_single = None
        self.port_edit_image_single = None
        
        # NEW: Added color input fields for ASCII modes
        self.color_edit_ascii_single = None
        self.bg_color_edit_ascii_single = None
        self.color_edit_ascii_threading = None
        self.bg_color_edit_ascii_threading = None
        
        self.init_ui()
        
    def init_ui(self):
        self.setWindowTitle("DreamDrawer - Another Owot Drawing Tool")
        self.setWindowIcon(QIcon(resource_path("favicon.ico")))
        # Fixed window size 506x622 - blocked from resizing
        self.setFixedSize(506, 622)
        
        # Set authentic Dreama theme
        self.set_Dreama_theme()
        
        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Main layout
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(6, 6, 6, 6)
        main_layout.setSpacing(4)

        # Custom PNG Header Image
        self.header_label = HeaderImageLabel()
        # Try to load header image - replace "header.png" with your actual image path
        header_loaded = self.header_label.set_header_image(resource_path("header.png"))
        main_layout.addWidget(self.header_label)
        
        # Subtitle (only show if using image header)
        if header_loaded:
            subtitle = QLabel("DreamDrawer v1.1")
            subtitle.setAlignment(Qt.AlignCenter)
            subtitle.setStyleSheet("""
                QLabel {
                    color: #808080;
                    font-family: 'Segoe UI';
                    font-size: 9pt;
                    padding: 1px;
                    background-color: transparent;
                }
            """)
            subtitle.setMinimumHeight(18)
            subtitle.setMaximumHeight(18)
            main_layout.addWidget(subtitle)
        
        # Create compact tabs
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #404040;
                background-color: #0a0a0a;
                top: -1px;
            }
            QTabBar::tab {
                background-color: #1a1a1a;
                color: #c0c0c0;
                padding: 4px 8px;
                border: 1px solid #404040;
                border-bottom: none;
                border-top-left-radius: 1px;
                border-top-right-radius: 1px;
                font-family: 'Segoe UI';
                font-size: 7.1pt;
                margin-right: 1px;
                min-width: 70px;
            }
            QTabBar::tab:selected {
                background-color: #0a0a0a;
                border-bottom: 1px solid #0a0a0a;
            }
            QTabBar::tab:hover {
                background-color: #2a2a2a;
            }
        """)
        self.tabs.setMinimumHeight(320)
        self.tabs.setMaximumHeight(320)
        
        # Create compact tabs
        self.ascii_single_tab = self.create_ascii_single_tab()
        self.ascii_threading_tab = self.create_ascii_threading_tab()
        self.image_single_tab = self.create_image_single_tab()
        self.image_threading_tab = self.create_image_threading_tab()
        
        self.tabs.addTab(self.ascii_single_tab, "ASCII Single")
        self.tabs.addTab(self.ascii_threading_tab, "ASCII Threading")
        self.tabs.addTab(self.image_single_tab, "Image Single")
        self.tabs.addTab(self.image_threading_tab, "Image Threading")
        
        main_layout.addWidget(self.tabs)
        
        # Control buttons
        button_layout = QHBoxLayout()
        
        self.deploy_btn = DreamaButton("Start Drawing")
        self.deploy_btn.clicked.connect(self.start_deployment)
        
        self.abort_btn = DreamaButton("Abort")
        self.abort_btn.clicked.connect(self.stop_deployment)
        self.abort_btn.setEnabled(False)
        
        self.clear_btn = DreamaButton("Clear Log")
        self.clear_btn.clicked.connect(self.clear_log)
        
        button_layout.addWidget(self.deploy_btn)
        button_layout.addWidget(self.abort_btn)
        button_layout.addWidget(self.clear_btn)
        button_layout.addStretch()
        
        main_layout.addLayout(button_layout)
        
        # Progress bar above deployment log
        self.progress_bar = DreamaProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setMinimumHeight(16)
        self.progress_bar.setMaximumHeight(16)
        main_layout.addWidget(self.progress_bar)
        
        # Log section
        log_label = QLabel("Progress Log:")
        log_label.setStyleSheet("color: #c0c0c0; font-family: 'Segoe UI'; font-size: 8pt; font-weight: bold;")
        log_label.setMinimumHeight(18)
        log_label.setMaximumHeight(18)
        main_layout.addWidget(log_label)
        
        self.log_text = DreamaTextEdit()
        self.log_text.setMinimumHeight(100)
        self.log_text.setMaximumHeight(100)
        main_layout.addWidget(self.log_text)
        
    def set_Dreama_theme(self):
        dark_palette = QPalette()
        dark_palette.setColor(QPalette.Window, QColor(10, 10, 10))
        dark_palette.setColor(QPalette.WindowText, QColor(192, 192, 192))
        dark_palette.setColor(QPalette.Base, QColor(0, 0, 0))
        dark_palette.setColor(QPalette.AlternateBase, QColor(10, 10, 10))
        dark_palette.setColor(QPalette.ToolTipBase, QColor(192, 192, 192))
        dark_palette.setColor(QPalette.ToolTipText, QColor(192, 192, 192))
        dark_palette.setColor(QPalette.Text, QColor(192, 192, 192))
        dark_palette.setColor(QPalette.Button, QColor(26, 26, 26))
        dark_palette.setColor(QPalette.ButtonText, QColor(192, 192, 192))
        dark_palette.setColor(QPalette.BrightText, Qt.red)
        dark_palette.setColor(QPalette.Link, QColor(0, 85, 255))
        dark_palette.setColor(QPalette.Highlight, QColor(0, 85, 255))
        dark_palette.setColor(QPalette.HighlightedText, Qt.black)
        self.setPalette(dark_palette)
        
    def create_ascii_single_tab(self):
        tab = CompactTabWidget()
        # File selection
        file_widget = self.create_file_widget("ASCII", self.browse_ascii_single_file)
        tab.add_group("File Configuration", file_widget)
        # Position
        pos_widget = self.create_position_widget("ascii_single")
        tab.add_group("Position", pos_widget)
        # Settings
        settings_widget = self.create_settings_widget("ascii_single")
        tab.add_group("Settings", settings_widget)
        # Color Settings
        color_widget = self.create_color_widget("ascii_single")
        tab.add_group("Color Settings", color_widget)
        # Proxy
        proxy_widget = self.create_proxy_widget("ascii_single")
        tab.add_group("Proxy", proxy_widget)
        return tab
        
    def create_ascii_threading_tab(self):
        tab = CompactTabWidget()
        # File selection
        file_widget = self.create_file_widget("ASCII", self.browse_ascii_threading_file)
        tab.add_group("File Configuration", file_widget)
        # Proxy file
        proxy_file_widget = self.create_proxy_file_widget("ascii_threading")
        tab.add_group("Proxy Configuration", proxy_file_widget)
        # Position
        pos_widget = self.create_position_widget("ascii_threading")
        tab.add_group("Position", pos_widget)
        # Settings
        settings_widget = self.create_settings_widget("ascii_threading")
        tab.add_group("Settings", settings_widget)
        # Color Settings
        color_widget = self.create_color_widget("ascii_threading")
        tab.add_group("Color Settings", color_widget)
        return tab
        
    def create_image_single_tab(self):
        tab = CompactTabWidget()
        # File selection
        file_widget = self.create_file_widget("Image", self.browse_image_single_file)
        tab.add_group("File Configuration", file_widget)
        # Position
        pos_widget = self.create_position_widget("image_single")
        tab.add_group("Position", pos_widget)
        # Settings
        settings_widget = self.create_settings_widget("image_single")
        tab.add_group("Settings", settings_widget)
        # Proxy
        proxy_widget = self.create_proxy_widget("image_single")
        tab.add_group("Proxy", proxy_widget)
        return tab
        
    def create_image_threading_tab(self):
        tab = CompactTabWidget()
        # File selection
        file_widget = self.create_file_widget("Image", self.browse_image_threading_file)
        tab.add_group("File Configuration", file_widget)
        # Proxy file
        proxy_file_widget = self.create_proxy_file_widget("image_threading")
        tab.add_group("Proxy Configuration", proxy_file_widget)
        # Position
        pos_widget = self.create_position_widget("image_threading")
        tab.add_group("Position", pos_widget)
        # Settings
        settings_widget = self.create_settings_widget("image_threading")
        tab.add_group("Settings", settings_widget)
        return tab
        
    def create_file_widget(self, file_type, browse_callback):
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)
        file_edit = DreamaLineEdit()
        file_edit.setPlaceholderText(f"Select {file_type} file...")
        
        # Store reference based on callback type
        if browse_callback == self.browse_ascii_single_file:
            self.ascii_file_edit = file_edit
        elif browse_callback == self.browse_ascii_threading_file:
            self.ascii_threading_file_edit = file_edit
        elif browse_callback == self.browse_image_single_file:
            self.image_file_edit = file_edit
        elif browse_callback == self.browse_image_threading_file:
            self.image_threading_file_edit = file_edit
        
        browse_btn = DreamaButton("Browse")
        browse_btn.setFixedWidth(50)
        browse_btn.clicked.connect(browse_callback)
        
        layout.addWidget(file_edit)
        layout.addWidget(browse_btn)
        
        return widget
        
    def create_proxy_file_widget(self, tab_type):
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)
        
        proxy_file_edit = DreamaLineEdit()
        proxy_file_edit.setPlaceholderText("Select proxy file...")
        
        # Store reference based on tab type
        if tab_type == "ascii_threading":
            self.proxy_file_edit_ascii_threading = proxy_file_edit
        elif tab_type == "image_threading":
            self.proxy_file_edit_image_threading = proxy_file_edit
        
        browse_btn = DreamaButton("Browse")
        browse_btn.setFixedWidth(50)
        browse_btn.clicked.connect(lambda: self.browse_proxy_file(tab_type))
        
        layout.addWidget(proxy_file_edit)
        layout.addWidget(browse_btn)
        
        return widget
        
    def create_position_widget(self, tab_type):
        widget = QWidget()
        layout = QGridLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)
        
        # Start X
        x_label = QLabel("Start X:")
        x_label.setStyleSheet("color: #c0c0c0; font-family: 'Segoe UI'; font-size: 8pt;")
        
        x_edit = DreamaLineEdit()
        x_edit.setText("0")
        x_edit.setMaximumWidth(50)
        
        # Start Y
        y_label = QLabel("Start Y:")
        y_label.setStyleSheet("color: #c0c0c0; font-family: 'Segoe UI'; font-size: 8pt;")
        
        y_edit = DreamaLineEdit()
        y_edit.setText("0")
        y_edit.setMaximumWidth(50)
        
        # Store references based on tab type
        if tab_type == "ascii_single":
            self.x_edit_ascii_single = x_edit
            self.y_edit_ascii_single = y_edit
        elif tab_type == "ascii_threading":
            self.x_edit_ascii_threading = x_edit
            self.y_edit_ascii_threading = y_edit
        elif tab_type == "image_single":
            self.x_edit_image_single = x_edit
            self.y_edit_image_single = y_edit
        elif tab_type == "image_threading":
            self.x_edit_image_threading = x_edit
            self.y_edit_image_threading = y_edit
        
        layout.addWidget(x_label, 0, 0)
        layout.addWidget(x_edit, 0, 1)
        layout.addWidget(y_label, 0, 2)
        layout.addWidget(y_edit, 0, 3)
        
        return widget
        
    def create_settings_widget(self, tab_type):
        widget = QWidget()
        layout = QGridLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)
        
        # Create separate wipe checkbox for each tab
        wipe_checkbox = DreamaCheckBox("Wipe Mode")
        
        # Store reference based on tab type
        if tab_type == "ascii_single":
            self.wipe_checkbox_ascii_single = wipe_checkbox
        elif tab_type == "ascii_threading":
            self.wipe_checkbox_ascii_threading = wipe_checkbox
        elif tab_type == "image_single":
            self.wipe_checkbox_image_single = wipe_checkbox
        elif tab_type == "image_threading":
            self.wipe_checkbox_image_threading = wipe_checkbox
        
        # Repeat
        repeat_label = QLabel("Repeat:")
        repeat_label.setStyleSheet("color: #c0c0c0; font-family: 'Segoe UI'; font-size: 8pt;")
        
        repeat_edit = DreamaLineEdit()
        repeat_edit.setText("1")
        repeat_edit.setMaximumWidth(35)
        
        # Chunk Size
        chunk_label = QLabel("Chunk:")
        chunk_label.setStyleSheet("color: #c0c0c0; font-family: 'Segoe UI'; font-size: 8pt;")
        
        chunk_edit = DreamaLineEdit()
        chunk_edit.setText("80")
        chunk_edit.setMaximumWidth(35)
        
        # Sleep
        sleep_label = QLabel("Sleep:")
        sleep_label.setStyleSheet("color: #c0c0c0; font-family: 'Segoe UI'; font-size: 8pt;")
        
        sleep_edit = DreamaLineEdit()
        sleep_edit.setText("0.17")
        sleep_edit.setMaximumWidth(35)
        
        # Store references based on tab type
        if tab_type == "ascii_single":
            self.repeat_edit_ascii_single = repeat_edit
            self.chunk_edit_ascii_single = chunk_edit
            self.sleep_edit_ascii_single = sleep_edit
        elif tab_type == "ascii_threading":
            self.repeat_edit_ascii_threading = repeat_edit
            self.chunk_edit_ascii_threading = chunk_edit
            self.sleep_edit_ascii_threading = sleep_edit
        elif tab_type == "image_single":
            self.repeat_edit_image_single = repeat_edit
            self.chunk_edit_image_single = chunk_edit
            self.sleep_edit_image_single = sleep_edit
        elif tab_type == "image_threading":
            self.repeat_edit_image_threading = repeat_edit
            self.chunk_edit_image_threading = chunk_edit
            self.sleep_edit_image_threading = sleep_edit
        
        layout.addWidget(wipe_checkbox, 0, 0, 1, 2)
        layout.addWidget(repeat_label, 0, 2)
        layout.addWidget(repeat_edit, 0, 3)
        layout.addWidget(chunk_label, 0, 4)
        layout.addWidget(chunk_edit, 0, 5)
        layout.addWidget(sleep_label, 0, 6)
        layout.addWidget(sleep_edit, 0, 7)
        
        return widget

    def create_color_widget(self, tab_type):
        """Create color input fields for ASCII tabs"""
        widget = QWidget()
        layout = QGridLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)
        
        color_label = QLabel("Color:")
        color_label.setStyleSheet("color: #c0c0c0; font-family: 'Segoe UI'; font-size: 8pt;")
        
        color_edit = DreamaLineEdit()
        color_edit.setMaximumWidth(70)
        color_edit.setPlaceholderText("#000000")
        
        bg_color_label = QLabel("BG Color:")
        bg_color_label.setStyleSheet("color: #c0c0c0; font-family: 'Segoe UI'; font-size: 8pt;")
        
        bg_color_edit = DreamaLineEdit()
        bg_color_edit.setMaximumWidth(70)
        bg_color_edit.setPlaceholderText("#f70004")
        
        # Store references based on tab type
        if tab_type == "ascii_single":
            self.color_edit_ascii_single = color_edit
            self.bg_color_edit_ascii_single = bg_color_edit
        elif tab_type == "ascii_threading":
            self.color_edit_ascii_threading = color_edit
            self.bg_color_edit_ascii_threading = bg_color_edit
        
        layout.addWidget(color_label, 0, 0)
        layout.addWidget(color_edit, 0, 1)
        layout.addWidget(bg_color_label, 0, 2)
        layout.addWidget(bg_color_edit, 0, 3)
        
        return widget
        
    def create_proxy_widget(self, tab_type):
        widget = QWidget()
        layout = QGridLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)
        
        host_label = QLabel("Host:")
        host_label.setStyleSheet("color: #c0c0c0; font-family: 'Segoe UI'; font-size: 8pt;")
        
        host_edit = DreamaLineEdit()
        host_edit.setPlaceholderText("host")
        host_edit.setMaximumWidth(70)
        
        port_label = QLabel("Port:")
        port_label.setStyleSheet("color: #c0c0c0; font-family: 'Segoe UI'; font-size: 8pt;")
        
        port_edit = DreamaLineEdit()
        port_edit.setPlaceholderText("port")
        port_edit.setMaximumWidth(45)
        
        # Store references based on tab type
        if tab_type == "ascii_single":
            self.host_edit_ascii_single = host_edit
            self.port_edit_ascii_single = port_edit
        elif tab_type == "image_single":
            self.host_edit_image_single = host_edit
            self.port_edit_image_single = port_edit
        
        layout.addWidget(host_label, 0, 0)
        layout.addWidget(host_edit, 0, 1)
        layout.addWidget(port_label, 0, 2)
        layout.addWidget(port_edit, 0, 3)
        
        return widget
        
    def browse_ascii_single_file(self):
        filename, _ = QFileDialog.getOpenFileName(
            self, "Select ASCII File", "", "Text Files (*.txt);;All Files (*)"
        )
        if filename and self.ascii_file_edit:
            self.ascii_file_edit.setText(filename)
            
    def browse_ascii_threading_file(self):
        filename, _ = QFileDialog.getOpenFileName(
            self, "Select ASCII File", "", "Text Files (*.txt);;All Files (*)"
        )
        if filename and self.ascii_threading_file_edit:
            self.ascii_threading_file_edit.setText(filename)
            
    def browse_image_single_file(self):
        filename, _ = QFileDialog.getOpenFileName(
            self, "Select Image File", "", 
            "Image Files (*.jpg *.jpeg *.png);;All Files (*)"
        )
        if filename and self.image_file_edit:
            self.image_file_edit.setText(filename)
            
    def browse_image_threading_file(self):
        filename, _ = QFileDialog.getOpenFileName(
            self, "Select Image File", "", 
            "Image Files (*.jpg *.jpeg *.png);;All Files (*)"
        )
        if filename and self.image_threading_file_edit:
            self.image_threading_file_edit.setText(filename)
            
    def browse_proxy_file(self, tab_type):
        filename, _ = QFileDialog.getOpenFileName(
            self, "Select Proxy File", "", "Text Files (*.txt);;All Files (*)"
        )
        if filename:
            if tab_type == "ascii_threading" and self.proxy_file_edit_ascii_threading:
                self.proxy_file_edit_ascii_threading.setText(filename)
            elif tab_type == "image_threading" and self.proxy_file_edit_image_threading:
                self.proxy_file_edit_image_threading.setText(filename)
            
    def clear_log(self):
        self.log_text.clear()
        
    def log_message(self, message):
        self.log_text.append(message)
        cursor = self.log_text.textCursor()
        cursor.movePosition(QTextCursor.End)
        self.log_text.setTextCursor(cursor)
        
    def start_deployment(self):
        if self.deployment_thread and self.deployment_thread.isRunning():
            return
            
        current_tab = self.tabs.currentIndex()
        modes = ["ascii_single", "ascii_threading", "image_single", "image_threading"]
        mode = modes[current_tab]
        
        if not self.validate_inputs(mode):
            return
            
        # Create args object
        class Args:
            pass
        args = Args()
        args.mode = mode
        args.server_url = self.server_url
        
        # FIXED: Get values from the correct tab-specific input fields
        if mode == "ascii_single":
            args.start_x = int(self.x_edit_ascii_single.text())
            args.start_y = int(self.y_edit_ascii_single.text())
            repeat_text = self.repeat_edit_ascii_single.text().strip().lower()
            if repeat_text == "inf":
                args.repeat = float('inf')
            else:
                args.repeat = int(repeat_text)
            args.chunk_size = int(self.chunk_edit_ascii_single.text())
            args.sleep_between = float(self.sleep_edit_ascii_single.text())
            args.wipe = "on" if self.wipe_checkbox_ascii_single.isChecked() else "off"
            args.ascii_file = self.ascii_file_edit.text() if self.ascii_file_edit else ""
            args.proxy_host = self.host_edit_ascii_single.text() or None
            args.proxy_port = int(self.port_edit_ascii_single.text()) if self.port_edit_ascii_single and self.port_edit_ascii_single.text() else None
            args.color = self.color_edit_ascii_single.text() if self.color_edit_ascii_single else "#000000"
            args.bg_color = self.bg_color_edit_ascii_single.text() if self.bg_color_edit_ascii_single else None
            
        elif mode == "ascii_threading":
            args.start_x = int(self.x_edit_ascii_threading.text())
            args.start_y = int(self.y_edit_ascii_threading.text())
            repeat_text = self.repeat_edit_ascii_threading.text().strip().lower()
            if repeat_text == "inf":
                args.repeat = float('inf')
            else:
                args.repeat = int(repeat_text)
            args.chunk_size = int(self.chunk_edit_ascii_threading.text())
            args.sleep_between = float(self.sleep_edit_ascii_threading.text())
            args.wipe = "on" if self.wipe_checkbox_ascii_threading.isChecked() else "off"
            args.ascii_file = self.ascii_threading_file_edit.text() if self.ascii_threading_file_edit else ""
            args.proxy_file = self.proxy_file_edit_ascii_threading.text() if self.proxy_file_edit_ascii_threading else ""
            if args.proxy_file:args.proxies = parse_proxy_file(args.proxy_file)
            else:args.proxies = []
            args.color = self.color_edit_ascii_threading.text() if self.color_edit_ascii_threading else "#000000"
            args.bg_color = self.bg_color_edit_ascii_threading.text() if self.bg_color_edit_ascii_threading else None
                
        elif mode == "image_single":
            args.start_x = int(self.x_edit_image_single.text())
            args.start_y = int(self.y_edit_image_single.text())
            repeat_text = self.repeat_edit_image_single.text().strip().lower()
            if repeat_text == "inf":
                args.repeat = float('inf')
            else:
                args.repeat = int(repeat_text)
            args.chunk_size = int(self.chunk_edit_image_single.text())
            args.sleep_between = float(self.sleep_edit_image_single.text())
            args.wipe = "on" if self.wipe_checkbox_image_single.isChecked() else "off"
            args.image_file = self.image_file_edit.text() if self.image_file_edit else ""
            args.proxy_host = self.host_edit_image_single.text() or None
            args.proxy_port = int(self.port_edit_image_single.text()) if self.port_edit_image_single and self.port_edit_image_single.text() else None
            
        elif mode == "image_threading":
            args.start_x = int(self.x_edit_image_threading.text())
            args.start_y = int(self.y_edit_image_threading.text())
            repeat_text = self.repeat_edit_image_threading.text().strip().lower()
            if repeat_text == "inf":
                args.repeat = float('inf')
            else:
                args.repeat = int(repeat_text)
            args.chunk_size = int(self.chunk_edit_image_threading.text())
            args.sleep_between = float(self.sleep_edit_image_threading.text())
            args.wipe = "on" if self.wipe_checkbox_image_threading.isChecked() else "off"
            args.image_file = self.image_threading_file_edit.text() if self.image_threading_file_edit else ""
            args.proxy_file = self.proxy_file_edit_image_threading.text() if self.proxy_file_edit_image_threading else ""
            if args.proxy_file:args.proxies = parse_proxy_file(args.proxy_file)
            else:args.proxies = []
        
        # Start deployment thread
        self.deployment_thread = DeploymentThread(args)
        self.deployment_thread.log_signal.connect(self.log_message)
        self.deployment_thread.finished_signal.connect(self.deployment_finished)
        
        self.deploy_btn.setEnabled(False)
        self.abort_btn.setEnabled(True)
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)  # Indeterminate progress
        
        self.deployment_thread.start()
        
    def stop_deployment(self):
        if self.deployment_thread and self.deployment_thread.isRunning():
            self.deployment_thread.stop()
            self.log_message("[INFO] Task aborted by user")
            self.deployment_finished(False)
            
    def deployment_finished(self, success):
        self.deploy_btn.setEnabled(True)
        self.abort_btn.setEnabled(False)
        self.progress_bar.setVisible(False)
        if not success:
            self.log_message("[ERROR] Task terminated")
            
    def validate_inputs(self, mode):
        if mode == "ascii_single":
            file_edit = self.ascii_file_edit
            file_type = "ASCII"
        elif mode == "ascii_threading":
            file_edit = self.ascii_threading_file_edit
            file_type = "ASCII"
        elif mode == "image_single":
            file_edit = self.image_file_edit
            file_type = "image"
        else:
            file_edit = self.image_threading_file_edit
            file_type = "image"
            
        if not file_edit or not file_edit.text():
            QMessageBox.critical(self, "Error", f"Please select a {file_type} file")
            return False
            
        if not os.path.exists(file_edit.text()):
            QMessageBox.critical(self, "Error", f"{file_type} file does not exist")
            return False
            
        if mode in ["ascii_threading", "image_threading"]:
            proxy_file_edit = None
            if mode == "ascii_threading":
                proxy_file_edit = self.proxy_file_edit_ascii_threading
            else:
                proxy_file_edit = self.proxy_file_edit_image_threading
            if not proxy_file_edit or not proxy_file_edit.text():
                QMessageBox.critical(self, "Error", "Please select a proxy file for threading mode")
                return False
            if not os.path.exists(proxy_file_edit.text()):
                QMessageBox.critical(self, "Error", "Proxy file does not exist")
                return False
                
        # Validate numeric fields from the correct tab
        try:
            if mode == "ascii_single":
                int(self.x_edit_ascii_single.text())
                int(self.y_edit_ascii_single.text())
                repeat_text = self.repeat_edit_ascii_single.text().strip().lower()
                if repeat_text != "inf":
                    int(repeat_text)
                int(self.chunk_edit_ascii_single.text())
                float(self.sleep_edit_ascii_single.text())
            elif mode == "ascii_threading":
                int(self.x_edit_ascii_threading.text())
                int(self.y_edit_ascii_threading.text())
                repeat_text = self.repeat_edit_ascii_threading.text().strip().lower()
                if repeat_text != "inf":
                    int(repeat_text)
                int(self.chunk_edit_ascii_threading.text())
                float(self.sleep_edit_ascii_threading.text())
            elif mode == "image_single":
                int(self.x_edit_image_single.text())
                int(self.y_edit_image_single.text())
                repeat_text = self.repeat_edit_image_single.text().strip().lower()
                if repeat_text != "inf":
                    int(repeat_text)
                int(self.chunk_edit_image_single.text())
                float(self.sleep_edit_image_single.text())
            elif mode == "image_threading":
                int(self.x_edit_image_threading.text())
                int(self.y_edit_image_threading.text())
                repeat_text = self.repeat_edit_image_threading.text().strip().lower()
                if repeat_text != "inf":
                    int(repeat_text)
                int(self.chunk_edit_image_threading.text())
                float(self.sleep_edit_image_threading.text())
        except ValueError:
            QMessageBox.critical(self, "Error", "Please check numeric fields (X, Y, Repeat, Chunk Size, Sleep)")
            return False
        return True

# Main application
if __name__ == "__main__":
    app = QApplication(sys.argv)
    # Enable high DPI scaling
    app.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    app.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    # Set compact font
    font = QFont("Segoe UI", 7)
    app.setFont(font)
    window = PixelArtGUI()
    window.show()
    sys.exit(app.exec_())