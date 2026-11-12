# AI4Bharat Indic Parler-TTS (Apache-2.0, gated: needs HF_TOKEN). Build context: repo root.
FROM eduvid/engine-base:1
RUN printf 'torch==2.5.1+cu124\ntorchaudio==2.5.1+cu124\n' > /etc/pip-constraints.txt
ENV PIP_CONSTRAINT=/etc/pip-constraints.txt PIP_EXTRA_INDEX_URL=https://download.pytorch.org/whl/cu124
COPY engines/tts-parler/requirements.txt /tmp/req.txt
RUN pip install -r /tmp/req.txt
COPY common /opt/common
RUN pip install /opt/common && pip check
COPY engines/tts_contract_test.py tests/test_contract.py
COPY engines/tts-parler/server.py .
ENV TEST_VOICE=divya
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]
