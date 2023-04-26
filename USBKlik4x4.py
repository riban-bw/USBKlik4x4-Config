# Configuration editor for TheKikGen USBKlik4x-Config
#
# Copyright: riban ltd (riban.co.uk)
# Licencse: GPL V3.0
# Source: https://github.com/riban-bw/USBKlik4x-Config
#
# Dependencies: tkinter, mido, PIL, ImageTk

from copy import copy
from tkinter import messagebox
import mido
import tkinter as tk
from tkinter import ttk
import logging
from PIL import ImageTk, Image
import ToolTips
from datetime import datetime
from time import sleep
from threading import Thread

sysex_header = [0x77, 0x77, 0x78]

credits = [
    'Code:',
    'riban.co.uk',
    'Tooltips',
    'pedrojhenriques.com',
    '',
    'Icons:',
    'https://freeicons.io',
    'profile/5790', # Transfer, Save
    'profile/3335', # Info
    'profile/730', # Restore
    'profile/6156', # Selected
    'https://freesvg.org', # LED
    'https://commons.wikimedia.org/wiki/File:DIN-5_Diagram.svg', # 5-pin DIN
    'https://www.freepik.com' # USB
]

PORT_TYPE = ["USB", "jack", "virtual", "ithru"]
PORT_TYPE_USB = 0
PORT_TYPE_JACK = 1
PORT_TYPE_VIRT = 2
PORT_TYPE_ITHRU = 3
PIPE_TYPE = ["filter", "note", "channel", "velocity", "cc", "clock", "loopback", "keyboard split", "velocity split"]
PIPE_COLOUR = ["red", "orange", "yellow", "green", "blue", "indigo", "violet", "brown", "black"]
PIPE_MSGFLTR = 0x00
PIPE_NOTECHG = 0x01
PIPE_CHANMAP = 0x02
PIPE_VELOCHG = 0x03
PIPE_CCCHANG = 0x04
PIPE_CLKDIVD = 0x05
PIPE_LOOPBCK = 0x06
PIPE_SLOTCHN = 0x07
PIPE_KBSPLIT = 0x08
PIPE_VLSPLIT = 0x09
usb_idle = 0
itellithru_routes = {}
routes = {} # list of dest ports indexed by "input_port_type:input_port:output_port_type"
port_slots = {}
pipelines = {} # [id, param 1, param 2, param 3, param 4] mapped by slot:pipe_index
midi_clock = [{"enabled": False, "bpm": 120, "mtc": False} for i in range(4)]
update_pending = False
selected_source = ""
selected_destination = ""
tmp_line = None # ID of a line being dragged out
ui_thread_running = True
selected_pipe = None

def send_sysex(payload):
    midi_out.send(mido.Message('sysex', data=sysex_header+payload))

def request_state(fast=False):
    global routes, port_slots, pipelines, itellithru_routes
    itellithru_routes = {}
    routes = {} # list of dest ports indexed by "input_port_type:input_port:output_port_type"
    port_slots = {}
    pipelines = {} # [id, param 1, param 2, param 3, param 4] mapped by slot:pipe_index
    if fast:
        send_sysex([0x05, 0x7F, 0x00, 0x00, 0x00])
        return
    # USB device settings
    send_sysex([0x05, 0x0B, 0x00, 0x00, 0x00])
    # MIDI clock settings
    for clock in range(4):
        send_sysex([0x05, 0x0C, clock, 0x00, 0x00])
    # USB idle
    send_sysex([0x05, 0x0E, 0x02, 0x00, 0x00])
    # IThru routing
    for port in range(8):
        send_sysex([0x05, 0x0E, 0x03, port, 0x00])
    # In port midi routing
    for type in range(3):
        for port in range(16):
            send_sysex([0x05, 0x0F, 0x01, type, port])
    # Bus mode settings
    send_sysex([0x05, 0x10, 0x00, 0x00, 0x00])
    # In port attached slot
    for type in range(4):
        for port in range(16):
            send_sysex([0x05, 0x11, 0x00, type, port])
    # Pipes in slot
    for slot in range(8):
        for idx in range(8):
            send_sysex([0x05, 0x11, 0x01, slot + 1, idx])

def hardware_reset():
    send_sysex([0x0A, 0xF7])

def request_id():
    send_sysex([0x01])

def toggle_sysex_ack():
    send_sysex([0x06, 0x02])

def sysex_ack():
    send_sysex([0x06, 0x03])

def factory_reset():
    send_sysex([0x06, 0x04])

def clear_all():
    send_sysex([0x06, 0x05])

def save_to_flash():
    send_sysex([0x06, 0x07])

def serial_config_mode():
    send_sysex([0x06, 0x08])

def update_mode():
    send_sysex([0x06, 0x98])

def set_product_string(name):
    lst = [0x0B, 0x00]
    for l in name:
        lst.append(ord(l))
    send_sysex(lst)

def set_product_vendor_product_id(id):
    id = id.replace(":", "")
    if len(id) != 8:
        return
    lst = [0x0B, 0x01]
    for l in id:
        if not l.isnumeric():
            return
        lst.append(ord(l))
    send_sysex(lst)

def enable_midi_clock(clock, enable=True):
    if clock < 0 or clock > 4:
        return
    if enable:
        send_sysex([0x0C, 0x00, clock, 1])
    else:
        send_sysex([0x0C, 0x00, clock, 1])

def set_bpm(clock, bpm):
    if clock < 0 or clock > 4:
        return
    if bpm > 300 or bpm < 10:
        return
    val = bpm * 10
    msbn = val >> 8 & 0x0F
    lsbn1 = val >> 4 & 0x0F
    lsbn2 = val >> 0 & 0x0F
    send_sysex([0x0C, 0x01, clock, msbn, lsbn1, lsbn2])

def enable_mtc(clock, enable=True):
    if clock != 0x7F and (clock < 0 or clock > 4):
        return
    if enable:
        send_sysex([0x0C, 0x02, clock, 1])
    else:
        send_sysex([0x0C, 0x02, clock, 0])

def reset_intelligent_thru():
    send_sysex([0x0E, 0x00])

def disable_intelligent_thru():
    send_sysex([0x0E, 0x01])

def set_usb_idle(duration):
    # F0 77 77 78 0E 02 < Number of 15s periods: 00-7F > F7
    send_sysex([0x0E, 0x02, duration // 15])

def set_jack_routing(in_port, out_ports):
    #F0 77 77 78 0E 03 <JackIn port > [<out port type> [<out ports list: nn...nn>] ] F7
    send_sysex([0x0E, 0x03, in_port] + out_ports) #TODO: Port types/ports???

def reset_midi_routing():
    send_sysex([0x0F, 00])

def set_midi_port_routing(src_type, src_port, dst_type, dst_ports):
    #F0 77 77 78 0F 01 <in port type> <in port> <out port type>[out ports list: nn...nn] F7
    send_sysex([0x0F, 0x01, src_type, src_port, dst_type] + dst_ports)

def enable_I2C(enable=True):
    #F0 77 77 78 10 00 < enable:1 | disable:0 > F7
    if enable:
        send_sysex([0x10, 0x00, 1])
    else:
        send_sysex([0x10, 0x00, 0])

def set_device_id(id):
    if id < 4 or id > 8:
        return
    send_sysex([0x10, 0x01] + [id])

def copy_slot(src, dst):
    if src < 1 or src > 8 or dst < 1 or dst > 8:
        return
    send_sysex([0x11, 0x00, 0x00, src, dst])

def clear_slot(slot):
    if slot != 0x7F and (slot < 1 or slot > 8):
        return
    send_sysex([0x11, 0x00, 0x01, slot])

'''
port_type : 0: cable, 1: jack, 2: virtual, 3: ithru
port : Port index 1..8
slot : Slot 1..8 or 0 to detach port from all slots
'''
def attach_port_to_slot(port_type, port, slot):
    if port_type < 0 or port_type > 3 or port < 0 or port > 16 or slot < 0 or slot > 8:
        return
    send_sysex([0x11, 0x00, 0x02, port_type, port, slot])

def add_pipe(slot, pipe, param_1, param_2, param_3, param_4):
    send_sysex([0x11, 0x00, slot, pipe, param_1, param_2, param_3, param_4])

def insert_pipe(slot, offset, pipe, param_1, param_2, param_3, param_4):
    send_sysex([0x11, 0x01, 0x01, slot, offset, pipe, param_1, param_2, param_3, param_4])

def replace_pipe(slot, offset, pipe, param_1, param_2, param_3, param_4):
    send_sysex([0x11, 0x01, 0x02, slot, offset, pipe, param_1, param_2, param_3, param_4])

def clear_pipe(slot, offset):
    send_sysex([0x11, 0x01, 0x03, slot, offset])

def clear_first_pipe(slot):
    send_sysex([0x11, 0x01, 0x04, slot])

def bypass_pipe(slot, pipe, bypass=True):
    if bypass:
        send_sysex([0x11, 0x01, 0x05, slot, pipe, 1])
    else:
        send_sysex([0x11, 0x01, 0x05, slot, pipe, 0])

def send_dump():
    #TODO: Implement send_dump
    pass

## UI  Functions ##

# Add and remove ALSA ports to global list of source ports 
def populate_devices(event=None):
    global klik_devices
    klik_devices = []
    for port in mido.get_input_names():
        if port.startswith("MidiKlik 4x") and port[port.rfind(':'):] == ":0":
            klik_devices.append(port)
    cmb_device['values'] = klik_devices

# Handle selection from MIDI source drop-down list
def device_changed(event=None):
    global midi_thread
    name = midi_device_port.get()
    if name not in klik_devices:
        return
    #TODO: Open port
    global midi_in, midi_out
    #TODO: Reuse MIDI ports
    try:
        midi_in.close()
        midi_out.close()
        global midi_thread_running
        midi_thread_running = False
        midi_thread.join()
    except:
        pass
    midi_in = mido.open_input(name)
    midi_out = mido.open_output(name)
    # Start MIDI listening thread
    midi_thread = Thread(target=midi_in_thread, args=())
    midi_thread.name = 'alsa_in'
    midi_thread.daemon = True
    midi_thread.start()

    request_state()

def pipe_type_changed(event):
    logging.warning("TODO: Pipe type change")

def restore_last_download():
    draw_routes()
    #TODO: Implement restore_last_download
    pass

def save():
    #TODO: Implement save
    pass

# Show application info (about...)
def show_info():
    msg = 'USBKliK4x-Config\nriban 2023\n'
    for credit in credits:
        msg += '\n{}'.format(credit)
    messagebox.showinfo('About...', msg)

# Show status message
#   msg: Text message to show in status bar
#   status: Influences display [0: Info (default), 1: Success, 2: Error]
def set_statusbar(msg, status=None):
    if status == 1:
        bg = '#aacf55'
    elif status == 2:
        bg = '#cc0000'
    else:
        bg = '#cccccc'
    lbl_statusbar.config(text=datetime.now().strftime('%H:%M:%S: ' + msg), background=bg)


# Handle MIDI data received
#   indata: List of raw MIDI data bytes
def handle_midi_input(data):
    #logging.warning(f"Rx: {data}")
    str = '[{}] '.format(len(data))
    for i in data:
        str += '{:02X} '.format(i)
    set_statusbar(str)

    if list(data[:3]) != sysex_header:
        return False
    if data[3:5] == (0x0B, 0x00):
        str = ""
        for i in data[5]:
            str += chr(i)
        product_string.set(str)
    elif data[3:5] == (0x0B, 0x01):
        vid_pid.set(f"{data[5]:x}{data[6]:x}{data[7]:x}{data[8]:x}:{data[9]:x}{data[10]:x}{data[11]:x}{data[12]:x}")
    elif data[3] == 0x0C:
        if data[5] > 3:
            return False
        if data[5] == 0:
            midi_clock[data[5]]["enabled"] = (data[6] == 1)
        elif data[4] == 0x01:
            midi_clock[data[5]]["bpm"] = ((data[6] << 8) + (data[7] << 4) + data[8]) / 10
        elif data[4] == 0x02:
            midi_clock[data[5]]["mtc"] = (data[6] == 1)
    elif data[3] == 0x0E:
        # Intelligent thru
        if data[4] == 2:
            global usb_idle
            usb_idle = 15 * data[5]
        elif data[4] == 3:
            input_port = data[5]
            output_ports = []
            if len(data) > 6:
                output_type = data[6]
                for port in data[7:]:
                    output_ports.append(port)
                global itellithru_routes
                itellithru_routes[f"{input_port}:{output_type}"] = output_ports
    elif data[3:5] == (0x0F, 0x01):
        # MIDI routing
        info = f"MIDI routing: {PORT_TYPE[data[5]]} {data[6]} => {PORT_TYPE[data[7]]}:"
        dests = []
        for out in data[8:]:
            info += f" {out}"
            dests.append(out)
        #logging.warning(info)
        global routes
        routes[f"{data[5]}:{data[6]}:{data[7]}"] = dests
    elif data[3] == 0x10:
        # Bus mode
        pass
    elif data[3:6] == (0x11, 0x00, 0x02):
        # Slot connections
        global port_slots
        port_slots[f"{data[6]}:{data[7]}"] = data[8]
    elif data[3:6] == (0x11, 0x01, 0x01):
        # Transformation pipelines
        slot = data[6]
        pipe_index = data[7]
        pipe_id = data[8]
        param_1 = data[9]
        param_2 = data[10]
        param_3 = data[11]
        param_4 = data[12]
        global pilelines
        pipelines[f"{slot}:{pipe_index}"] = data[8:13]
    #Ack send_sysex([0x06, 0x03, 1])
    else:
        return False
    return True

# Thread worker listening for ALSA MIDI events
def midi_in_thread():
    global midi_thread_running, update_pending
    midi_thread_running = True
    while midi_thread_running:
        msg = midi_in.receive(block=False)
        if msg:
            if msg.type == 'sysex':
                update_pending |= handle_midi_input(msg.data)
        else:
            sleep(0.01)

# Thread worker to refresh UI
def ui_thread_worker():
    global update_pending
    while ui_thread_running:
        while not update_pending:
            if not ui_thread_running:
                return
            sleep(0.1)
        update_pending = False
        sleep(0.4)
        if not update_pending:
            draw_routes()

##################################### 
## Core sequential functional code ##
##################################### 

## Initialise MIDI interfaces ##
midi_in = mido.open_input()
midi_out = mido.open_output()

# Create UI
klik_devices = [] # List of available USBKlik 4x devices

# Root window
root = tk.Tk()
root.grid_columnconfigure(0, weight=1)
root.grid_rowconfigure(3, weight=1)
root.title('riban USBKliK4x editor')

# Icons
img_transfer_down = ImageTk.PhotoImage(Image.open('transfer.png'))
img_transfer_up = ImageTk.PhotoImage(Image.open('transfer.png').rotate(180))
img_save = ImageTk.PhotoImage(Image.open('save.png'))
img_info = ImageTk.PhotoImage(Image.open('info.png'))
img_restore = ImageTk.PhotoImage(Image.open('restore.png'))
port_images = {}
port_images[PORT_TYPE_JACK] = ImageTk.PhotoImage(Image.open('din5.png'))
port_images[PORT_TYPE_USB] = ImageTk.PhotoImage(Image.open('usb.png'))

tk.Label(root, text='riban USBKliK4x editor', bg='#80cde0').grid(columnspan=2, sticky='ew')

# Top frame
frame_top = tk.Frame(root, padx=2, pady=2)
frame_top.columnconfigure(7, weight=1)
frame_top.grid(row=1, columnspan=2, sticky='enw')

midi_device_port = tk.StringVar()
ttk.Label(frame_top, text='USBKlik Device').grid(row=0, column=0, sticky='w')
cmb_device = ttk.Combobox(frame_top, textvariable=midi_device_port, state='readonly')
cmb_device.bind('<<ComboboxSelected>>', device_changed)
cmb_device.grid(row=1, column=0, sticky='n')
cmb_device.bind('<Enter>', populate_devices)

ttk.Label(frame_top, text='VID:PID').grid(row=0, column=1, sticky='n')
vid_pid = tk.StringVar()
txt_vid_pid =ttk.Label(frame_top, textvar=vid_pid).grid(row=1, column=1, sticky='w')
product_string = tk.StringVar()

btn_download = ttk.Button(frame_top, image=img_transfer_down, command=request_state)
btn_download.grid(row=0, column=2, rowspan=2)
btn_upload = ttk.Button(frame_top, image=img_transfer_up, command=send_dump)
btn_upload.grid(row=0, column=3, rowspan=2)
btn_save = ttk.Button(frame_top, image=img_save, command=save)
btn_save.grid(row=0, column=4, rowspan=2)
btn_restore = ttk.Button(frame_top, image=img_restore, command=restore_last_download)
btn_restore.grid(row=0, column=5, rowspan=2)
btn_info = ttk.Button(frame_top, image=img_info, command=show_info)
btn_info.grid(row=0, column=6, rowspan=2)
device_info = tk.StringVar()
lbl_device_info = tk.Label(frame_top, textvariable=device_info)
lbl_device_info.grid(row=0, column=7, sticky='ne')

pipe_type = tk.StringVar()
cmb_pipe_type = ttk.Combobox(frame_top, textvariable=pipe_type, state='readonly')
cmb_pipe_type.bind('<<ComboboxSelected>>', pipe_type_changed)
cmb_pipe_type.grid(row=2, column=0, sticky='n')
cmb_pipe_type['values'] = PIPE_TYPE

canvas = tk.Canvas(root, width=800, height=600)
canvas.grid(row=3, column=0, sticky='nsew')
src_usb = []
dst_widgets = [] # List of [type,index,icon]
src_widgets = [] # List of [type,index,icon]

lbl_statusbar = ttk.Label(root, anchor='w', width=1, background='#cccccc') # width=<any> stops long messages stretching width of display
lbl_statusbar.grid(row=4, column=0, columnspan=2, sticky='ew')

def connect(src, dst):
    '''Connect two MIDI ports
    src - [type, index]
    dst = [type, index]
    '''

    #logging.warning(f"Connect {src} from {dst}")
    key = f"{src[0]}:{src[1]}:{dst[0]}"
    try:
        if dst[1] in routes[key]:
            return
        routes[key].append(dst[1])
        set_midi_port_routing(src[0], src[1], dst[0], routes[key])
        draw_routes()
    except Exception as e:
        logging.warning(e)
    
def disconnect(src, dst):
    '''Disconnect two MIDI ports
    src - [type, index]
    dst = [type, index]
    '''

    #logging.warning(f"Disconnect {src} from {dst}")
    key = f"{src[0]}:{src[1]}:{dst[0]}"
    try:
        if dst[1] not in routes[key]:
            return
        routes[key].remove(dst[1])
        set_midi_port_routing(src[0], src[1], dst[0], routes[key])
        draw_routes()
    except Exception as e:
        logging.warning(e)

def select_click(x, y):
    '''Update the global selected_source or selected_destination from the clicked coordinates
    x - x coordinate of click
    y - y coordinate of click
    '''

    global selected_source, selected_destination
    selected_source = None
    selected_destination = None
    try:
        widget = canvas.find_closest(x, y)[0]
    except Exception as e:
        logging.warning(e)
        return

    for w in src_widgets:
        if widget == w[2]:
            selected_source = [w[0], w[1]]
            break
    if selected_source is None:
        for w in dst_widgets:
            if widget == w[2]:
                selected_destination = [w[0], w[1]]
                break
    if selected_source or selected_destination:
        return widget

def on_src_click(event):
    '''Handle left mouse click on MIDI input'''

    global selected_source, tmp_line
    widget = select_click(event.x, event.y)
    if widget is None:
        return

    if selected_source:
        if selected_source[0] == PORT_TYPE_JACK:
            offset = 0
        elif selected_source[0] == PORT_TYPE_USB:
            offset = 9 * 40
        else:
            return
        tmp_line = canvas.create_line(52, offset + 16 + selected_source[1] * 40, 52, offset + 16 + selected_source[1] * 40, fill="blue", width=3)

def on_src_release(event):
    '''Handle left mouse release on MIDI input'''

    global tmp_line, selected_source
    canvas.delete(tmp_line)
    tmp_line = None
    try:
        widget = event.widget.find_closest(event.x + 1, event.y + 1)[0]
        dest = None
        for w in dst_widgets:
            if widget == w[2]:
                dest = [w[0], w[1]]
                break
        if selected_source is not None and dest is not None:
            connect(selected_source, dest)
    except Exception as e:
        logging.warning(e)
    selected_source = None

def on_src_drag(event):
    '''Handle mouse drag from MIDI input'''

    try:
        coords = canvas.coords(tmp_line)
        canvas.coords(tmp_line, coords[0], coords[1], event.x, event.y)
    except:
        pass

def on_src_context(event):
    '''Handle right mouse click on MIDI input'''

    widget = select_click(event.x, event.y)
    if widget is None:
        return
    jack_dests = [[PORT_TYPE_JACK, routes[f"{selected_source[0]}:{selected_source[1]}:{PORT_TYPE_JACK}"]]]
    usb_dests = [[PORT_TYPE_USB, routes[f"{selected_source[0]}:{selected_source[1]}:{PORT_TYPE_USB}"]]]
    if selected_source[0] == PORT_TYPE_USB:
        dests = usb_dests + jack_dests
    else:
        dests = jack_dests + usb_dests
    if len(dests):
        m = tk.Menu(root)
        for a in dests:
            for b in a[1]:
                m.add_command(label = f"Disconnect from {PORT_TYPE[a[0]]} {b + 1}", command=lambda x=[a[0], b]: disconnect(selected_source, x))
        m.tk_popup(event.x_root, event.y_root)

def on_dst_context(event):
    '''Handle right mouse click on MIDI output'''

    widget = select_click(event.x, event.y)
    if widget is None:
        return

    m = tk.Menu(root)
    connected = False
    for src, dst in routes.items():
        parts = src.split(':')
        if str(selected_destination[0]) == parts[2] and selected_destination[1] in dst:
            m.add_command(label = f"Disconnect from {PORT_TYPE[int(parts[0])]} {int(parts[1]) + 1}", command=lambda x=[(int(parts[0])), (int(parts[1]))]: disconnect(x, selected_destination))
            connected = True
    if connected:
        m.tk_popup(event.x_root, event.y_root)

def on_pipe_click(event):
    logging.warning("TODO: Pipe click")
    try:
        widget = canvas.find_closest(event.x, event.y)[0]
        slot, pipe, type = canvas.gettags(widget)[0].split(":")
        pipe_type.set(PIPE_TYPE[int(type)])
    except Exception as e:
        logging.warning(e)
        return    
    pass

def draw_routes():
    '''Draw the routing graph'''
    
    global src_widgets, dst_widgets, canvas
    try:
        canvas.delete(tk.ALL)
        src_widgets = []
        dst_widgets = []

        for port in range(9): #TODO: Define quanity of ports
            for type in range(2):
                if type == PORT_TYPE_USB:
                    offset = 9 * 40
                else:
                    offset = 0
                # Sources
                canvas.create_text(0, 16 + offset + port * 40, text=f"{port+1}", anchor="w")
                src_widgets.append([type, port, canvas.create_image(20, offset + port * 40, image=port_images[type], anchor="nw", tags=("src"))])
                canvas.tag_bind("src", '<ButtonPress-1>', on_src_click)
                canvas.tag_bind("src", '<ButtonRelease-1>', on_src_release)
                canvas.tag_bind("src", '<Motion>', on_src_drag)
                canvas.tag_bind("src", '<Button-3>', on_src_context)

                # Slots
                try:
                    slot = port_slots[f"{type}:{port}"]
                    if slot:
                        canvas.create_rectangle(60, offset + port * 40, 80, offset + port * 40 + 32, width=2, fill="white", tags=("pipe"))
                        canvas.create_text(70, offset + port * 40 + 16, text=f"{slot}")
                        for pipe in range(8):
                            processor = pipelines[f"{slot}:{pipe}"]
                            proc_type = processor[0]
                            colour = PIPE_COLOUR[proc_type]
                            r = canvas.create_rectangle(80 + pipe * 32, offset + port * 40, 110 + pipe * 32, offset + port * 40 + 32, width=2, fill=colour, tags=f"{slot}:{pipe}:{proc_type}")
                            canvas.tag_bind(r, '<Button-1>', on_pipe_click)
                except:
                    pass

                # Destinations
                if type == PORT_TYPE_USB:
                    offset = 0
                else:
                    offset = 9 * 40
                canvas.create_text(800, 16 + offset + port * 40, text=f"{port+1}", anchor="e")
                dst_widgets.append([type, port, canvas.create_image(780, offset + port * 40, image=port_images[type], anchor="ne", tags=("dst"))])
                canvas.tag_bind("dst", '<Button-3>', on_dst_context)

            # Route lines between source DIN and destination Cable
            for dst in routes[f"{PORT_TYPE_JACK}:{port}:{PORT_TYPE_USB}"]:
                canvas.create_line(52, 16 + port * 40, 748, 16 + dst * 40, fill="blue", width=3, tags=("wire"))
            # Route lines between source DIN and destination DIN
            for dst in routes[f"{PORT_TYPE_JACK}:{port}:{PORT_TYPE_JACK}"]:
                canvas.create_line(52, 16 + port * 40, 748, 9*40 + 16 + dst * 40, fill="blue", width=3, tags=("wire"))
            # Route lines between source USB and destination DIN
            for dst in routes[f"{PORT_TYPE_USB}:{port}:{PORT_TYPE_JACK}"]:
                canvas.create_line(52, 9*40 + 16 + port * 40, 748, 9*40 + 16 + dst * 40, fill="blue", width=3, tags=("wire"))
            # Route lines between source USB and destination USB
            for dst in routes[f"{PORT_TYPE_USB}:{port}:{PORT_TYPE_USB}"]:
                canvas.create_line(52, 9*40 + 16 + port * 40, 748, 16 + dst * 40, fill="blue", width=3, tags=("wire"))
            canvas.tag_lower("wire")
    except:
        pass

tooltip_obj = ToolTips.ToolTips(
    [btn_download, btn_upload, btn_save, btn_restore, btn_info],
    ['Download from USBKlik4x', 'Upload to USBKlik4x', 'Save config on USBKlik4x', 'Restore from flash', 'About']
)

# Attempt to autoconnect to first detected klik device
populate_devices()
try:
    midi_device_port.set(klik_devices[0])
    device_changed()
except:
    pass

ui_thread = Thread(target=ui_thread_worker, args=())
ui_thread.name = 'ui'
ui_thread.daemon = True
ui_thread.start()

root.mainloop()

ui_thread_running = False
midi_thread_running = False
ui_thread.join()
midi_thread.join()