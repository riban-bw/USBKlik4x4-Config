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
from os import system
try:
    import jack
except:
    logging.warning("Jack not available")

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

MAX_PORT = 9
MAX_CHAIN = 8
MAX_SLOT = 8
ICON_SIZE = 32
WIDTH = 900
PORT_TYPE = ["USB", "jack", "virtual", "ithru"]
PORT_TYPE_USB = 0
PORT_TYPE_JACK = 1
PORT_TYPE_VIRT = 2
PORT_TYPE_ITHRU = 3
PROC_TYPE = ["filter", "transpose", "map", "velocity", "cc", "clock divide", "loopback", "chain channel", "keyboard split", "velocity split"]
PROC_COLOUR = ["CornflowerBlue", "cornsilk4", "MediumAquamarine", "SkyBlue3", "goldenrod", "LightPink3", "plum3", "OliveDrab4", "yellow4", "MediumPurple3"]
PROC_FLTR = 0x00
PROC_NOTECHG = 0x01
PROC_CHANMAP = 0x02
PROC_VELOCHG = 0x03
PROC_CCCHANG = 0x04
PROC_CLKDIVD = 0x05
PROC_LOOPBCK = 0x06
PROC_SLOTCHN = 0x07
PROC_KBSPLIT = 0x08
PROC_VLSPLIT = 0x09
PROCESSORS = {
    "filter": {
        "value": PROC_FLTR,
        "param": {
            "type": "cmb",
            "values": {
                "include": {
                    "value" : 0,
                    "param": {
                        "type": "bitmask",
                        "values": {
                            "Voice": {
                                "value": 1
                            },
                            "System": {
                                "value": 2
                            },
                            "Realtime": {
                                "value": 4
                            },
                            "SysEx": {
                                "value": 8
                            }
                        }
                    }
                },
                "exclude": {
                    "value": 1,
                    "param": {
                        "type": "bitmask",
                        "values": {
                            "Voice": {
                                "value": 1
                            },
                            "System": {
                                "value": 2
                            },
                            "Realtime": {
                                "value": 4
                            },
                            "SysEx": {
                                "value": 8
                            }
                        }
                    }
                },
                "MIDI Status": {
                    "value": 2,
                    "param": {
                        "type": "cmb",
                        "values": {
                            "Include": {
                                "value": 0
                            },
                            "Exclude": {
                                "value": 1
                            }
                        }
                    }
                },
                "MIDI Channel": {
                    "value": 3,
                    "param": {
                        "type": "cmb",
                        "values": {
                            "Include": {
                                "value": 0
                            },
                            "Exclude": {
                                "value": 1
                            }
                        }
                    }
                }
            }
        }
    }
}

DEFAULT_PARAMS = [
    [0x01, 0x04, 0x00, 0x00],
    [0x00, 0x01, 0x00, 0x00],
    [0x00, 0x00, 0x00, 0x00],
    [0x00, 0x00, 0x7F, 0x00],
    [0x00, 0x00, 0x00, 0x00],
    [0x02, 0x00, 0x00, 0x00],
    [0x03, 0x01, 0x00, 0x00],
    [0x01, 0x00, 0x00, 0x00],
    [0x00, 0x00, 0x00, 0x00],
    [0x40, 0x00, 0x00, 0x00]
]


usb_idle = 0
itellithru_routes = {}
routes = {} # Dictionary of dest ports indexed by "input_port_type:input_port:output_port_type"
port_chains = {} # Index of chain connected to a port, mapped by 'port_type:port_index'
chains = [ {} for i in range(MAX_CHAIN)] # List of chains. Each chains is a dictionary of slots, indexed by slot id. Each slot contains a list of [proc_type, param1, param2, param3, param4]
midi_clock = [{"enabled": False, "bpm": 120, "mtc": False} for i in range(4)]
update_pending = False
selected_source = None # [type,index]
selected_destination = None # [type,index]
tmp_line = None # ID of a line being dragged out
ui_thread_running = True
selected_processor = None # Index of currently selected processor
selected_chain = None # Index of currently selected chain
selected_source = None
selected_destination = None
selected_proc_type = None
try:
    jack_client = jack.Client("riban_usbklik4x")
except:
    jack_client = None

def send_sysex(payload):
    midi_port.send(mido.Message('sysex', data=sysex_header+payload))

def refresh_chain(chain): 
    if chain < 1 or chain > MAX_CHAIN:
        return
    chains[chain - 1] = {}
    for slot in range(MAX_SLOT):
        send_sysex([0x05, 0x11, 0x01, chain, slot])

def request_state(fast=False):
    global routes, port_chains, chains, itellithru_routes
    itellithru_routes = {}
    routes = {}
    port_chains = {}
    chains = [{} for i in range(MAX_CHAIN)]
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
    for port in range(MAX_PORT):
        send_sysex([0x05, 0x0E, 0x03, port, 0x00])
    # In port midi routing
    for type in range(3):
        for port in range(MAX_PORT):
            send_sysex([0x05, 0x0F, 0x01, type, port])
    # Bus mode settings
    send_sysex([0x05, 0x10, 0x00, 0x00, 0x00])
    # Input port attached chain
    for type in range(4):
        for port in range(MAX_PORT):
            send_sysex([0x05, 0x11, 0x00, type, port])
    # Processors in chains
    for chain in range(1, MAX_CHAIN + 1):
        for slot in range(MAX_SLOT):
            send_sysex([0x05, 0x11, 0x01, chain, slot])

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

def copy_chain(src, dst):
    if src < 1 or src > 8 or dst < 1 or dst > MAX_CHAIN:
        return
    send_sysex([0x11, 0x00, 0x00, src, dst])

def clear_chain(chain):
    if chain != 0x7F and (chain < 1 or chain > MAX_CHAIN):
        return
    send_sysex([0x11, 0x00, 0x01, chain])
    refresh_chain(chain)

'''
port_type : 0: cable, 1: jack, 2: virtual, 3: ithru
port : Port index 1..8
chain : Chain 1..8 or 0 to detach port from all chains
'''
def attach_port_to_slot(port_type, port, chain):
    if port_type < 0 or port_type >= 3 or port < 0 or port >= MAX_PORT or chain < 0 or chain > MAX_CHAIN:
        return
    send_sysex([0x11, 0x00, 0x02, port_type, port, chain])
    send_sysex([0x05, 0x11, 0x00, port_type, port])

def get_default_params(proc_type, param_1, param_2, param_3, param_4):
    if param_1 is None:
        return DEFAULT_PARAMS[proc_type]
    return [param_1, param_2, param_3, param_4]

def add_processor(chain, proc_type, param_1=None, param_2=None, param_3=None, param_4=None):
    params = get_default_params(proc_type, param_1, param_2, param_3, param_4)
    send_sysex([0x11, 0x01, 0x00, chain, proc_type] + params)
    refresh_chain(chain)


def insert_processor(chain, offset, proc_type, param_1=None, param_2=None, param_3=None, param_4=None):
    params = get_default_params(proc_type, param_1, param_2, param_3, param_4)
    send_sysex([0x11, 0x01, 0x01, chain, offset, proc_type] + params)
    refresh_chain(chain)

def replace_processor(chain, offset, proc_type, param_1, param_2, param_3, param_4):
    params = get_default_params(proc_type, param_1, param_2, param_3, param_4)
    send_sysex([0x11, 0x01, 0x02, chain, offset, proc_type] + params)

def remove_processor(chain, offset):
    send_sysex([0x11, 0x01, 0x03, chain, offset])
    refresh_chain(chain)

def clear_first_chain(chain):
    send_sysex([0x11, 0x01, 0x04, chain])

def bypass_chain(chain, slot, bypass=True):
    if bypass:
        send_sysex([0x11, 0x01, 0x05, chain, slot, 1])
    else:
        send_sysex([0x11, 0x01, 0x05, chain, slot, 0])

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
    name = midi_device_port.get()
    if name not in klik_devices:
        return
    device_dst_port = None
    device_src_port = None
    try:
        for port in jack_client.get_ports(is_midi=True, is_input=True, is_physical=True):
            for alias in port.aliases:
                if alias.endswith('0-MidiKlik-4x-UMK-4X-IN'):
                    device_dst_port = port
                    break
            if device_dst_port:
                break
        for port in jack_client.get_ports(is_midi=True, is_output=True, is_physical=True):
            for alias in port.aliases:
                if alias.endswith('0-MidiKlik-4x-UMK-4X-OUT'):
                    device_src_port = port
                    break
            if device_src_port:
                break
        own_dst = jack_client.get_ports("ribanUSBKlik4x", is_input=True)[0]
        own_src = jack_client.get_ports("ribanUSBKlik4x", is_output=True)[0]

        jack_client.connect(device_src_port, own_dst)
        jack_client.connect(own_src, device_dst_port)
    except:
        try:
            system(f"aconnect '{midi_port.input.name}' '{name}'")
            system(f"aconnect '{name}' '{midi_port.output.name}'")
        except:
            pass

    request_state()

def get_control(root, proc):
    ret_val = []
    if "type" not in root:
        return None
    if root["type"] == "check":
        for name, content in root["values"].items():
            ctrl = ttk.Checkbutton(frame_top, text=name, onvalue=int(content["value"]), command=proc[3])
            ret_val.append(ctrl)
        pass
    elif root["type"] == "bitmask":
        value = 0
        try:
            value = int(proc[0].get())
        except:
            pass
        for i, name in enumerate(root["values"]):
            val = int(root["values"][name]["value"])
            a = tk.IntVar()
            ctrl = ttk.Checkbutton(frame_top, variable=a, text=name, onvalue=val, command=proc[3])
            if (value & val) == val:
                a.set(val)
            ret_val.append(ctrl)
    elif root["type"] == "cmb":
        ctrl = ttk.Combobox(frame_top, textvariable=proc[0], state='readonly')
        ctrl.bind('<<ComboboxSelected>>', proc[3])
        values = []
        for val in root['values']:
            values.append(val)
        ctrl['values'] = values
        ret_val.append(ctrl)
    return ret_val

def update_proc_editor():
    global proc_params
    for proc in proc_params:
        for ctrl in proc[1]:
            ctrl.grid_forget()
            del ctrl
        proc[1] = []
    try:
        tree_root = PROCESSORS[proc_type.get()]
        for proc in proc_params:
            ctrls = get_control(tree_root["param"], proc)
            for i, ctrl in enumerate(ctrls):
                ctrl.grid(row=1+i, column = proc[2], sticky="nw")
            proc[1] = ctrls
            tree_root = tree_root["param"]["values"][proc[0].get()]
    except Exception as e:
        logging.warning(e)
    pass

def proc_type_changed(event):
    update_proc_editor()

def proc_param_1_changed(event=None):
    logging.warning("TODO: Processor parameter 1")
    update_proc_editor()

def proc_param_2_changed(event=None):
    param = proc_params[1]
    ctrls = param[1]
    if type(ctrls[0]) == ttk.Checkbutton:
        value = 0
        for ctrl in ctrls:
            if 'selected' in ctrl.state():
                value += ctrl['onvalue']
        param[0].set(value)

    logging.warning("TODO: Processor parameter 2")
    update_proc_editor()

def proc_param_3_changed(event=None):
    logging.warning("TODO: Processor parameter 3")
    update_proc_editor()

def proc_param_4_changed(event=None):
    logging.warning("TODO: Processor parameter 4")
    update_proc_editor()

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
        global port_chains
        port_chains[f"{data[6]}:{data[7]}"] = data[8]
    elif data[3:6] == (0x11, 0x01, 0x01):
        # Transformation chains
        chain = data[6]
        slot = data[7]
        if chain > 0 and chain <= MAX_CHAIN:
            chains[chain - 1][slot] = data[8:]
    #Ack send_sysex([0x06, 0x03, 1])
    else:
        return False
    return True

# Thread worker listening for ALSA MIDI events
def midi_in_thread():
    global midi_thread_running, update_pending
    midi_thread_running = True
    while midi_thread_running:
        msg = midi_port.receive(block=False)
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

def resize_canvas(event):
    global WIDTH
    WIDTH = event.width
    draw_routes()

##################################### 
## Core sequential functional code ##
##################################### 

## Initialise MIDI interfaces ##
midi_port = mido.open_ioport('ribanUSBKlik4x', virtual=True)

# Create UI
klik_devices = [] # List of available USBKlik 4x devices

# Root window
root = tk.Tk()
root.grid_columnconfigure(0, weight=1)
canvas_row = 30
root.grid_rowconfigure(canvas_row, weight=1)
root.title('riban USBKlik4x editor')

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

column = 0

# USB MIDI Device
midi_device_port = tk.StringVar()
ttk.Label(frame_top, text='USBKlik Device').grid(row=0, column=column, sticky='w')
cmb_device = ttk.Combobox(frame_top, textvariable=midi_device_port, state='readonly')
cmb_device.bind('<<ComboboxSelected>>', device_changed)
cmb_device.grid(row=1, column=0, sticky='n')
cmb_device.bind('<Enter>', populate_devices)
column += 1

# Processor editor
ttk.Label(frame_top, text="Processor Type").grid(row=0, column=column, sticky='n')
proc_type = tk.StringVar()
cmb_proc_type = ttk.Combobox(frame_top, textvariable=proc_type, state='readonly')
cmb_proc_type.bind('<<ComboboxSelected>>', proc_type_changed)
cmb_proc_type.grid(row=1, column=column, sticky='n')
cmb_proc_type['values'] = PROC_TYPE
column += 1
proc_params = []
fn = [proc_param_1_changed, proc_param_2_changed, proc_param_3_changed, proc_param_4_changed]
for i in range(4):
    proc_params.append([tk.StringVar(), [], column, fn[i]])
    root.columnconfigure(column, weight=1)
    column += 1

# VID:PID
ttk.Label(frame_top, text='VID:PID').grid(row=0, column=column, sticky='n')
vid_pid = tk.StringVar()
txt_vid_pid =ttk.Label(frame_top, textvar=vid_pid).grid(row=1, column=column, sticky='w')
product_string = tk.StringVar()
column += 1

# Buttons
btn_download = ttk.Button(frame_top, image=img_transfer_down, command=request_state)
btn_download.grid(row=0, column=column, rowspan=2)
column += 1
btn_upload = ttk.Button(frame_top, image=img_transfer_up, command=send_dump)
btn_upload.grid(row=0, column=column, rowspan=2)
column += 1
btn_save = ttk.Button(frame_top, image=img_save, command=save)
btn_save.grid(row=0, column=column, rowspan=2)
column += 1
btn_restore = ttk.Button(frame_top, image=img_restore, command=restore_last_download)
btn_restore.grid(row=0, column=column, rowspan=2)
column += 1
btn_info = ttk.Button(frame_top, image=img_info, command=show_info)
btn_info.grid(row=0, column=column, rowspan=2)
column += 1
device_info = tk.StringVar()
lbl_device_info = tk.Label(frame_top, textvariable=device_info)
lbl_device_info.grid(row=0, column=column, sticky='ne')
column += 1

# Routing canvas
canvas = tk.Canvas(root, width=900, height=800)
canvas.bind('<Configure>', resize_canvas)
canvas.grid(row=canvas_row, column=0, sticky='nsew')
src_usb = []
dst_widgets = [] # List of [type,index,icon]
src_widgets = [] # List of [type,index,icon]

lbl_statusbar = ttk.Label(root, anchor='w', width=1, background='#cccccc') # width=<any> stops long messages stretching width of display
lbl_statusbar.grid(row=canvas_row+1, column=0, columnspan=2, sticky='ew')

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
    global selected_chain, selected_processor, selected_proc_type
    selected_source = None
    selected_destination = None
    selected_processor = None
    selected_chain = None
    selected_processor = None
    selected_proc_type = None
    
    try:
        widget = canvas.find_closest(x, y)[0]
        tags = canvas.gettags(widget)
        parts = tags[0].split(":")
        if "src" in tags:
            selected_source = [int(parts[0]), int(parts[1])]
        elif "dst" in tags:
            selected_destination = [int(parts[0]), int(parts[1])]
        elif "proc" in tags:
            selected_chain = int(parts[0])
            selected_processor = int(parts[1])
            selected_proc_type = int(parts[2])
        elif "chain" in tags:
            selected_chain = int(tags[0])
        else:
            return None
    except Exception as e:
        logging.warning(e)
        return

    return widget

def on_src_click(event):
    '''Handle left mouse click on MIDI input'''

    global selected_source, tmp_line
    widget = select_click(event.x, event.y)
    if widget is None:
        return

    if selected_source:
        if selected_source[0] == PORT_TYPE_JACK:
            offset = 4
        elif selected_source[0] == PORT_TYPE_USB:
            offset = 4 + 9 * 40
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
    m = tk.Menu(root)
    for a in dests:
        for b in a[1]:
            m.add_command(label=f"Disconnect from {PORT_TYPE[a[0]]} {b + 1}", command=lambda x=[a[0], b]: disconnect(selected_source, x))
    m.add_separator()
    current_chain = port_chains[f"{selected_source[0]}:{selected_source[1]}"]
    if current_chain:
        m.add_command(label=f"Detach from chain {current_chain}", command=lambda x=selected_source[0], y=selected_source[1]: attach_port_to_slot(selected_source[0], selected_source[1], 0))
        m.add_separator()
    for chain in range(1, MAX_CHAIN + 1):
        if chain != current_chain:
            m.add_command(label=f"Attach to chain {chain}", command=lambda x=selected_source[0], y=selected_source[1], chain=chain: attach_port_to_slot(selected_source[0], selected_source[1], chain))

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

def on_proc_click(event):
    global selected_chain, selected_processor, selected_proc_type
    logging.warning("TODO: Processor click")
    try:
        widget = select_click(event.x, event.y)
        tag = canvas.gettags(widget)[0]
        proc_type.set(PROC_TYPE[int(selected_proc_type)])
        canvas.itemconfig("proc_border", width=0)
        canvas.itemconfig(f"{tag}_border", width=4)

    except Exception as e:
        logging.warning(e)
        return    
    pass

def on_proc_release(event):
    pass

def on_proc_drag(event):
    pass

def on_proc_context(event):
    '''Handle right mouse click on pipe'''

    widget = select_click(event.x, event.y)
    if widget is None:
        return
    m = tk.Menu(root)
    m.add_command(label=f"Remove {PROC_TYPE[selected_proc_type]} processor", command=lambda x=selected_chain, y=selected_processor: remove_processor(x, y))
    m.add_separator()
    for proc_type, name in enumerate(PROC_TYPE):
        m.add_command(label=f"Insert {name}", command=lambda x=selected_chain, y=selected_processor, z=proc_type: insert_processor(x, y, z))
    m.tk_popup(event.x_root, event.y_root)

def on_chain_click(event):
    logging.warning("TODO: slot click")

def on_chain_release(event):
    pass

def on_chain_drag(event):
    pass

def on_chain_context(event):
    '''Handle right mouse click on slot'''

    widget = select_click(event.x, event.y)
    if widget is None:
        return
    m = tk.Menu(root)
    m.add_command(label = f"Clear chain {selected_chain}", command=lambda x=selected_chain: clear_chain(x))
    #m.add_command(label=f"Disconnect chain {selected_chain} from {PORT_TYPE[selected_source[0]]} {selected_source[1]}", command=lambda x=selected_source[0], y=selected_source[1], z=selected_chain: attach_port_to_slot(selected_source[0], selected_source[1], selected_chain))
    m.add_separator()
    for proc_type, name in enumerate(PROC_TYPE):
        m.add_command(label=f"Add {name}", command=lambda x=selected_chain, y=proc_type: add_processor(x, y))
    m.tk_popup(event.x_root, event.y_root)

def draw_routes():
    '''Draw the routing graph'''
    
    global src_widgets, dst_widgets, canvas
    try:
        canvas.delete(tk.ALL)
        src_widgets = []
        dst_widgets = []
        v_space = ICON_SIZE + 8
        if WIDTH < 800:
            width = 800
        else:
            width = WIDTH
        proc_width = (width - 140) // 8

        for port in range(MAX_PORT):
            for type in range(2):
                if type == PORT_TYPE_USB:
                    offset = 4 + MAX_PORT * v_space
                else:
                    offset = 4
                # Sources
                canvas.create_text(
                    0,
                   ICON_SIZE//2 + offset + port * v_space,
                   text=f"{port+1}",
                   anchor="w")
                tag = f"{type}:{port}"
                src_widgets.append(
                    [
                        type,
                        port,
                        canvas.create_image(
                            20,
                            offset + port * v_space,
                            image=port_images[type],
                            anchor="nw",
                            tags=(tag, "src")
                        )
                    ]
                )

                # Chains
                try:
                    chain = port_chains[f"{type}:{port}"]
                    if chain:
                        canvas.create_rectangle(
                            60,
                            offset + port * v_space,
                            80,
                            offset + port * v_space + ICON_SIZE,
                            width=0,
                            fill="white",
                            tags=(chain, "chain")
                        )
                        canvas.create_text(
                            70,
                            offset + port * v_space + ICON_SIZE//2,
                            text=f"{chain}",
                            tags=(chain, "chain")
                        )
                        for slot in range(MAX_SLOT):
                            try:
                                processor = chains[chain - 1][slot]
                                proc_type = processor[0]
                                colour = PROC_COLOUR[proc_type]
                                tag=f"{chain}:{slot}:{proc_type}"
                                canvas.create_rectangle(
                                    80 + slot * proc_width, 
                                    offset + port * v_space - 2, 
                                    80 + (slot + 1) * proc_width, 
                                    offset + port * v_space + ICON_SIZE + 2, 
                                    width=0, fill=colour, outline="red", 
                                    tags=(tag, "proc", f"{tag}_border", "proc_border")
                                    )
                                canvas.create_text(
                                    80 + proc_width // 2 + proc_width * slot,
                                    offset + port * v_space + ICON_SIZE // 2,
                                    text=PROC_TYPE[proc_type].replace(" ", "\n"),
                                    fill="white",
                                    justify=tk.CENTER,
                                    tags=(tag, "proc"))
                            except:
                                pass # No processor in this slot
                except:
                    pass

                # Destinations
                if type == PORT_TYPE_USB:
                    offset = 4
                else:
                    offset = 4 + MAX_PORT * v_space
                tag = f"{type}:{port}"
                canvas.create_text(
                    width,
                    ICON_SIZE//2 + offset + port * v_space,
                    text=f"{port+1}",
                    anchor="e"
                )
                dst_widgets.append(
                    [
                        type,
                        port,
                        canvas.create_image(
                            width - 20,
                            offset + port * v_space,
                            image=port_images[type],
                            anchor="ne",
                            tags=(tag, "dst")
                        )
                    ]
                )

            # Route lines between source DIN and destination Cable
            for dst in routes[f"{PORT_TYPE_JACK}:{port}:{PORT_TYPE_USB}"]:
                canvas.create_line(
                    52,
                    ICON_SIZE // 2 + port * v_space,
                    width - 52,
                    ICON_SIZE // 2 + dst * v_space,
                    fill="blue",
                    width=3,
                    tags=("wire")
                )
            # Route lines between source DIN and destination DIN
            for dst in routes[f"{PORT_TYPE_JACK}:{port}:{PORT_TYPE_JACK}"]:
                canvas.create_line(
                    52,
                    ICON_SIZE // 2 + port * v_space,
                    width - 52,
                    MAX_PORT * v_space + ICON_SIZE // 2 + dst * v_space,
                    fill="blue",
                    width=3,
                    tags=("wire")
                )
            # Route lines between source USB and destination DIN
            for dst in routes[f"{PORT_TYPE_USB}:{port}:{PORT_TYPE_JACK}"]:
                canvas.create_line(
                    52,
                    MAX_PORT * v_space + ICON_SIZE // 2 + port * v_space,
                    width - 52,
                    MAX_PORT * v_space + ICON_SIZE // 2 + dst * v_space,
                    fill="blue",
                    width=3,
                    tags=("wire")
                )
            # Route lines between source USB and destination USB
            for dst in routes[f"{PORT_TYPE_USB}:{port}:{PORT_TYPE_USB}"]:
                canvas.create_line(
                    52,
                    MAX_PORT * v_space + ICON_SIZE // 2 + port * v_space,
                    width - 52,
                    ICON_SIZE // 2 + dst * v_space,
                    fill="blue",
                    width=3,
                    tags=("wire")
                )
            canvas.tag_lower("wire")
    except:
        pass
    canvas.tag_bind("src", '<ButtonPress-1>', on_src_click)
    canvas.tag_bind("src", '<ButtonRelease-1>', on_src_release)
    canvas.tag_bind("src", '<Motion>', on_src_drag)
    canvas.tag_bind("src", '<Button-3>', on_src_context)
    canvas.tag_bind("dst", '<Button-3>', on_dst_context)
    canvas.tag_bind("chain", '<Button-1>', on_chain_click)
    canvas.tag_bind("chain", '<ButtonRelease-1>', on_chain_release)
    canvas.tag_bind("chain", '<Motion>', on_chain_drag)
    canvas.tag_bind("chain", '<Button-3>', on_chain_context)
    canvas.tag_bind("proc", '<Button-1>', on_proc_click)
    canvas.tag_bind("proc", '<ButtonRelease-1>', on_proc_release)
    canvas.tag_bind("proc", '<Motion>', on_proc_drag)
    canvas.tag_bind("proc", '<Button-3>', on_proc_context)

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

# Start UI thread
ui_thread = Thread(target=ui_thread_worker, args=())
ui_thread.name = 'ui'
ui_thread.daemon = True
ui_thread.start()

# Start MIDI listening thread
midi_thread = Thread(target=midi_in_thread, args=())
midi_thread.name = 'midi_in'
midi_thread.daemon = True
midi_thread.start()

# Start main UI thread
root.mainloop()

ui_thread_running = False
midi_thread_running = False
ui_thread.join()
midi_thread.join()