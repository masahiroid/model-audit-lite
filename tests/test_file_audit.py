from model_audit_lite.audit.files import is_risky_pickle


def test_real_pickle_formats_are_flagged():
    for name in ["pytorch_model.bin", "model.pt", "w.pth", "x.pkl", "a/b/c.ckpt"]:
        assert is_risky_pickle(name), name


def test_coreml_weight_blob_is_not_pickle():
    assert not is_risky_pickle("m_seq128_fp16.mlpackage/Data/com.apple.CoreML/weights/weight.bin")


def test_bin_outside_coreml_still_flagged():
    assert is_risky_pickle("model.mlpackage/other/data.bin")
    assert is_risky_pickle("weights/weight.bin")


def test_safe_formats_not_flagged():
    for name in ["model.safetensors", "m.gguf", "m.onnx", "m.tflite", "config.json"]:
        assert not is_risky_pickle(name), name
