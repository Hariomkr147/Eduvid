import speech_recognition as sr
from scipy.io import wavfile
import json

r = sr.Recognizer()
lines_data = json.load(open('videos/area-volume/data/lines.json', encoding='utf-8'))['lines']
sr_rate, audio = wavfile.read('videos/area-volume/data/narration.wav')

with open('recognized_new.txt', 'w', encoding='utf-8') as out:
    for idx, item in enumerate(lines_data):
        st = item['start']
        en = item['end']
        chunk = audio[int(st * sr_rate) : int(en * sr_rate)]
        wavfile.write('temp_slice.wav', sr_rate, chunk)
        
        with sr.AudioFile('temp_slice.wav') as s:
            a = r.record(s)
            
        try:
            hi = r.recognize_google(a, language='hi-IN')
        except Exception as e:
            hi = f'<FAIL: {e}>'
            
        try:
            en_txt = r.recognize_google(a, language='en-IN')
        except Exception as e:
            en_txt = f'<FAIL: {e}>'
            
        out.write(f"Line {idx:02d} ({st:.2f}s - {en:.2f}s)\n")
        out.write(f"  Script:  {item['text']}\n")
        out.write(f"  Hi ASR:  {hi}\n")
        out.write(f"  En ASR:  {en_txt}\n\n")

print("Recognized all lines to recognized_new.txt")
