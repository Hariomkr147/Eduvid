# WhisperX large-v3 transcription + forced alignment (wav2vec2; MMS_FA fallback). Build context: repo root.
FROM eduvid/engine-base:1
RUN printf 'torch==2.5.1+cu124\ntorchaudio==2.5.1+cu124\n' > /etc/pip-constraints.txt
ENV PIP_CONSTRAINT=/etc/pip-constraints.txt PIP_EXTRA_INDEX_URL=https://download.pytorch.org/whl/cu124
COPY engines/asr-whisperx/requirements.txt /tmp/req.txt
RUN pip install -r /tmp/req.txt
COPY common /opt/common
RUN pip install /opt/common && pip check
# whisperx 3.4.5 pins ctranslate2<4.5, which is built against cuDNN 8 (torch uses cuDNN 9).
# cuDNN 8 libs have different sonames (libcudnn_ops_infer.so.8 ...), so both coexist: unpack the cuDNN 8
# wheel into /opt/cudnn8 without installing it into the venv.
RUN pip download --no-deps -d /tmp/cudnn8 nvidia-cudnn-cu12==8.9.7.29 \
 && python -c "import zipfile,glob; zipfile.ZipFile(glob.glob('/tmp/cudnn8/*.whl')[0]).extractall('/opt/cudnn8')" \
 && rm -rf /tmp/cudnn8
ENV LD_LIBRARY_PATH=/opt/cudnn8/nvidia/cudnn/lib:${LD_LIBRARY_PATH}
COPY engines/asr-whisperx/tests tests
COPY engines/asr-whisperx/server.py .
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]
