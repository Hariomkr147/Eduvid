# Kokoro-82M via kokoro-onnx on onnxruntime-gpu (falls back to CPU). Build context: repo root.
FROM eduvid/engine-base:1
COPY engines/tts-kokoro/requirements.txt /tmp/req.txt
# kokoro-onnx hard-depends on the CPU onnxruntime; swap in the CUDA 12 / cuDNN 9 build (same module name).
RUN pip install -r /tmp/req.txt \
 && pip uninstall -y onnxruntime \
 && pip install --no-deps onnxruntime-gpu==1.20.2 coloredlogs flatbuffers protobuf sympy packaging humanfriendly "mpmath<1.4"
COPY common /opt/common
RUN pip install /opt/common && (pip check > /tmp/pipcheck.txt || true) \
 && cat /tmp/pipcheck.txt \
 && ! grep -v -e 'requires onnxruntime, which is not installed' -e 'No broken' /tmp/pipcheck.txt
COPY engines/tts_contract_test.py tests/test_contract.py
COPY engines/tts-kokoro/server.py .
ENV TEST_VOICE=am_michael TEST_TEXT="The curved surface area of a cylinder is two pi r h."
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]
