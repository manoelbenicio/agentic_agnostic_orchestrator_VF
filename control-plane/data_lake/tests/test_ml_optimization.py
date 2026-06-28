from data_lake.ml_optimization import ModelOptimizer

def test_model_optimizer():
    optimizer = ModelOptimizer(target_format="onnx", quantize=True)
    result = optimizer.optimize_model("s3://models/v1.pt", "s3://models/v1_opt.onnx")
    
    assert result["original_model"] == "s3://models/v1.pt"
    assert result["optimized_model"] == "s3://models/v1_opt.onnx"
    assert result["format"] == "onnx"
    assert result["quantized"] is True
    assert result["size_reduction"] == "60%"
    assert result["latency_improvement"] == "45%"
