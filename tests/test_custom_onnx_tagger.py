import io
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
from PIL import Image
from starlette.datastructures import Headers, UploadFile

from backend.app.config import settings
from backend.app.enums import FileTypeEnum, RatingEnum
from backend.app.models import Media, User
from backend.app.routes.ai_tagger import (
    PredictTagsRequest,
    TestModelRequest,
    WDTaggerSettingsRequest,
    delete_model,
    get_model_status,
    get_models,
    get_settings,
    predict_tags,
    predict_tags_batch,
    BatchPredictRequest,
    test_model,
    update_settings,
    upload_custom_model,
)
from backend.app.services.wd_tagger import (
    BUILTIN_MODEL_CONFIGS,
    ModelInferenceConfig,
    WDTagger,
    apply_output_postprocessing,
    clamp_model_config,
    clamp_threshold,
    custom_model_manager,
    get_wd_tagger,
    parse_label_data,
    prepare_image,
)
from tests.test_base import AsyncBackupTestBase


def _pb_varint(n: int) -> bytes:
    if n < 0:
        n += 1 << 64
    out = bytearray()
    while n >= 0x80:
        out.append((n & 0x7F) | 0x80)
        n >>= 7
    out.append(n)
    return bytes(out)


def _pb_field_varint(field_num: int, val: int) -> bytes:
    return _pb_varint((field_num << 3) | 0) + _pb_varint(val)


def _pb_field_bytes(field_num: int, data: bytes | str) -> bytes:
    raw = data.encode("utf-8") if isinstance(data, str) else data
    return _pb_varint((field_num << 3) | 2) + _pb_varint(len(raw)) + raw


def _onnx_dim_val(n: int) -> bytes:
    return _pb_field_varint(1, n)


def _onnx_dim_param(name: str) -> bytes:
    return _pb_field_bytes(2, name)


def _onnx_value_info(name: str, elem_type: int, dims: list[bytes]) -> bytes:
    shape_proto = b"".join(_pb_field_bytes(1, d) for d in dims)
    tensor_type = _pb_field_varint(1, elem_type) + _pb_field_bytes(2, shape_proto)
    type_proto = _pb_field_bytes(1, tensor_type)
    return _pb_field_bytes(1, name) + _pb_field_bytes(2, type_proto)


def _onnx_attr_ints(name: str, vals: list[int]) -> bytes:
    return (
        _pb_field_bytes(1, name)
        + _pb_field_varint(20, 7)
        + b"".join(_pb_field_varint(8, v) for v in vals)
    )


def _onnx_attr_int(name: str, val: int) -> bytes:
    return _pb_field_bytes(1, name) + _pb_field_varint(20, 2) + _pb_field_varint(3, val)


def _onnx_tensor_f32(name: str, dims: list[int], values: list | np.ndarray) -> bytes:
    raw = np.asarray(values, dtype="<f4").tobytes()
    return (
        b"".join(_pb_field_varint(1, d) for d in dims)
        + _pb_field_varint(2, 1)
        + _pb_field_bytes(8, name)
        + _pb_field_bytes(9, raw)
    )


def _onnx_external_tensor_f32(name: str, dims: list[int], location: str, raw_bytes: bytes) -> bytes:
    def kv_entry(k: str, v: str) -> bytes:
        return _pb_field_bytes(1, k) + _pb_field_bytes(2, v)

    return (
        b"".join(_pb_field_varint(1, d) for d in dims)
        + _pb_field_varint(2, 1)
        + _pb_field_bytes(8, name)
        + _pb_field_bytes(13, kv_entry("location", location))
        + _pb_field_bytes(13, kv_entry("offset", "0"))
        + _pb_field_bytes(13, kv_entry("length", str(len(raw_bytes))))
        + _pb_field_varint(14, 1)  # DataLocation.EXTERNAL = 1
    )


def _onnx_node(op_type: str, inputs: list[str], outputs: list[str], attrs: list[bytes] = ()) -> bytes:
    return (
        b"".join(_pb_field_bytes(1, i) for i in inputs)
        + b"".join(_pb_field_bytes(2, o) for o in outputs)
        + _pb_field_bytes(4, op_type)
        + b"".join(_pb_field_bytes(5, a) for a in attrs)
    )


def build_synthetic_onnx(
    scores: list[float],
    input_size: int = 64,
    nchw: bool = False,
    fixed_batch_one: bool = False,
    external_data_filename: str | None = None,
    dynamic_spatial: bool = False,
) -> tuple[bytes, bytes | None]:
    """Build a minimal valid ONNX model returning deterministic scores for any image."""
    num_classes = len(scores)
    bias_arr = np.asarray([scores], dtype="<f4")
    raw_bias = bias_arr.tobytes()

    if external_data_filename:
        bias_init = _onnx_external_tensor_f32("bias", [1, num_classes], external_data_filename, raw_bias)
        ext_bytes = raw_bias
    else:
        bias_init = _onnx_tensor_f32("bias", [1, num_classes], bias_arr)
        ext_bytes = None

    zero_init = _onnx_tensor_f32("zero", [1], [0.0])

    n1 = _onnx_node("ReduceMean", ["input"], ["mean_val"], [_onnx_attr_ints("axes", [1, 2, 3]), _onnx_attr_int("keepdims", 0)])
    n2 = _onnx_node("Mul", ["mean_val", "zero"], ["zero_batch"])
    n3 = _onnx_node("Unsqueeze", ["zero_batch"], ["zero_2d"], [_onnx_attr_ints("axes", [1])])
    n4 = _onnx_node("Add", ["zero_2d", "bias"], ["output"])

    batch_dim = _onnx_dim_val(1) if fixed_batch_one else _onnx_dim_param("batch")
    h_dim = _onnx_dim_param("height") if dynamic_spatial else _onnx_dim_val(input_size)
    w_dim = _onnx_dim_param("width") if dynamic_spatial else _onnx_dim_val(input_size)
    if nchw:
        in_dims = [batch_dim, _onnx_dim_val(3), h_dim, w_dim]
    else:
        in_dims = [batch_dim, h_dim, w_dim, _onnx_dim_val(3)]
    out_dims = [batch_dim, _onnx_dim_val(num_classes)]

    graph = (
        b"".join(_pb_field_bytes(1, n) for n in (n1, n2, n3, n4))
        + _pb_field_bytes(2, "test_tagger_graph")
        + _pb_field_bytes(5, bias_init)
        + _pb_field_bytes(5, zero_init)
        + _pb_field_bytes(11, _onnx_value_info("input", 1, in_dims))
        + _pb_field_bytes(12, _onnx_value_info("output", 1, out_dims))
    )
    opset = _pb_field_bytes(1, "") + _pb_field_varint(2, 11)
    model_bytes = _pb_field_varint(1, 7) + _pb_field_bytes(7, graph) + _pb_field_bytes(8, opset)
    return model_bytes, ext_bytes


def make_upload_file(filename: str, content: bytes, content_type: str = "application/octet-stream") -> UploadFile:
    return UploadFile(
        file=io.BytesIO(content),
        filename=filename,
        headers=Headers({"content-type": content_type}),
    )


class TestLabelAndPreprocessingUnits(unittest.TestCase):
    def test_parse_all_supported_label_formats(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            # 1. CSV with Danbooru categories + literal 'null'/'nan' tag names
            csv_path = root / "selected_tags.csv"
            csv_path.write_text(
                "tag_id,name,category,count\n"
                "1,1girl,0,100\n"
                "2,null,1,50\n"
                "3,touhou,3,80\n"
                "4,hakurei_reimu,4,70\n"
                "5,highres,5,90\n"
                "6,general,9,99\n",
                encoding="utf-8",
            )
            parsed_csv = parse_label_data(str(csv_path))
            self.assertEqual(parsed_csv["names"], ["1girl", "null", "touhou", "hakurei_reimu", "highres", "general"])
            self.assertEqual(parsed_csv["general"].tolist(), [0])
            self.assertEqual(parsed_csv["artist"].tolist(), [1])
            self.assertEqual(parsed_csv["copyright"].tolist(), [2])
            self.assertEqual(parsed_csv["character"].tolist(), [3])
            self.assertEqual(parsed_csv["meta"].tolist(), [4])
            self.assertEqual(parsed_csv["rating"].tolist(), [5])

            # 2. PixAI v1.0 JSON
            pixai_path = root / "pixai.json"
            pixai_path.write_text(
                json.dumps({
                    "categories": [
                        {"name": "general", "offset": 0, "count": 2, "tags": ["1girl", "solo"]},
                        {"name": "character", "offset": 2, "count": 1, "tags": ["miku"]},
                        {"name": "style", "offset": 3, "count": 1, "tags": ["some_artist"]},
                    ]
                }),
                encoding="utf-8",
            )
            parsed_pixai = parse_label_data(str(pixai_path))
            self.assertEqual(parsed_pixai["num_labels"], 4)
            self.assertEqual(parsed_pixai["character"].tolist(), [2])
            self.assertEqual(parsed_pixai["artist"].tolist(), [3])

            # 3. Camie metadata JSON
            camie_path = root / "camie-meta.json"
            camie_path.write_text(
                json.dumps({
                    "dataset_info": {
                        "tag_mapping": {
                            "idx_to_tag": {"0": "scenery", "1": "frieren"},
                            "tag_to_category": {"scenery": "general", "frieren": "character"},
                        }
                    }
                }),
                encoding="utf-8",
            )
            parsed_camie = parse_label_data(str(camie_path))
            self.assertEqual(parsed_camie["label_format"], "camie_json")
            self.assertEqual(parsed_camie["character"].tolist(), [1])

            # 4. Flat dict JSON & TXT
            dict_path = root / "flat.json"
            dict_path.write_text(json.dumps({"cat_ears": 0, "tail": 1}), encoding="utf-8")
            self.assertEqual(parse_label_data(str(dict_path))["names"], ["cat_ears", "tail"])

            txt_path = root / "tags.txt"
            txt_path.write_text("monochrome\ngreyscale\n\n", encoding="utf-8")
            self.assertEqual(parse_label_data(str(txt_path))["names"], ["monochrome", "greyscale"])

    def test_clamping_and_postprocessing(self):
        clamped = clamp_model_config({
            "batch_size": 999,
            "temperature": -2.0,
            "input_size": 12,
            "input_layout": "INVALID",
            "norm_mean": [-99.0, 0.5, 99.0],
            "norm_std": [0.0, 0.5, 50.0],
            "output_index": 42,
        })
        self.assertEqual(clamped.batch_size, 64)
        self.assertEqual(clamped.temperature, 0.05)
        self.assertEqual(clamped.input_size, 64)
        self.assertEqual(clamped.input_layout, "nhwc")
        self.assertEqual(clamped.norm_mean, (-10.0, 0.5, 10.0))
        self.assertEqual(clamped.norm_std, (0.001, 0.5, 10.0))
        self.assertEqual(clamped.output_index, 15)
        self.assertEqual(clamp_threshold(-1.5, 0.35), 0.0)
        self.assertEqual(clamp_threshold(2.5, 0.35), 1.0)

        # Auto activation detects logits outside [0, 1] -> sigmoid
        logits = np.array([[2.0, -2.0]], dtype=np.float32)
        probs_auto, resolved = apply_output_postprocessing(logits, "auto", temperature=1.0)
        self.assertEqual(resolved, "sigmoid")
        self.assertTrue(np.all((probs_auto > 0.0) & (probs_auto < 1.0)))

        # Higher temperature softens confidence toward 0.5 for both sigmoid and probability inputs
        probs_soft_logits, _ = apply_output_postprocessing(logits, "sigmoid", temperature=2.0)
        self.assertLess(probs_soft_logits[0, 0], probs_auto[0, 0])

        raw_probs = np.array([[0.9, 0.1]], dtype=np.float32)
        probs_soft_none, resolved_none = apply_output_postprocessing(raw_probs, "none", temperature=2.0)
        self.assertEqual(resolved_none, "none")
        self.assertLess(probs_soft_none[0, 0], 0.9)
        self.assertGreater(probs_soft_none[0, 1], 0.1)

    def test_prepare_image_modes_and_dtypes(self):
        img = Image.new("RGBA", (120, 80), (255, 0, 0, 255))
        cfg = ModelInferenceConfig(
            input_size=64,
            input_layout="nchw",
            color_space="rgb",
            resize_mode="stretch",
            interpolation="bilinear",
            normalization="imagenet",
        )
        arr_fp16 = prepare_image(img, config=cfg, target_dtype=np.float16)
        self.assertEqual(arr_fp16.shape, (3, 64, 64))
        self.assertEqual(arr_fp16.dtype, np.float16)


class TestCustomOnnxTaggerIntegration(AsyncBackupTestBase):
    def setUp(self):
        super().setUp()
        custom_model_manager.reload_from_disk()
        get_wd_tagger().unload_model()
        self.admin_user = User(username="admin")

    def tearDown(self):
        get_wd_tagger().unload_model()
        super().tearDown()

    async def test_namespace_collision_immunity_both_directions(self):
        # 1. Upload a custom model with the EXACT same name as built-in 'wd-eva02-large-tagger-v3'
        onnx_bytes, _ = build_synthetic_onnx([0.91, 0.15, 0.88], input_size=64, nchw=False)
        csv_bytes = (
            "tag_id,name,category,count\n"
            "1,1girl,0,100\n"
            "2,solo,0,90\n"
            "3,hakurei_reimu,4,80\n"
        ).encode("utf-8")

        resp1 = await upload_custom_model(
            files=[
                make_upload_file("model.onnx", onnx_bytes),
                make_upload_file("selected_tags.csv", csv_bytes),
            ],
            name="wd-eva02-large-tagger-v3",
            current_user=self.admin_user,
        )
        self.assertTrue(resp1["success"])
        m1 = resp1["model"]
        self.assertEqual(m1["id"], "custom:wd-eva02-large-tagger-v3")
        self.assertEqual(m1["display_name"], "wd-eva02-large-tagger-v3")
        self.assertTrue(m1["is_custom"])

        # 2. Upload a SECOND custom replica with the same name -> receives unique -2 slug
        resp2 = await upload_custom_model(
            files=[
                make_upload_file("model.onnx", onnx_bytes),
                make_upload_file("selected_tags.csv", csv_bytes),
            ],
            name="wd-eva02-large-tagger-v3",
            current_user=self.admin_user,
        )
        self.assertEqual(resp2["model"]["id"], "custom:wd-eva02-large-tagger-v3-2")

        # 3. Both built-in and custom replicas coexist in settings and models list
        settings_data = await get_settings(current_user=self.admin_user)
        ids = [m["id"] for m in settings_data["models"]]
        self.assertIn("wd-eva02-large-tagger-v3", ids)
        self.assertIn("custom:wd-eva02-large-tagger-v3", ids)
        self.assertIn("custom:wd-eva02-large-tagger-v3-2", ids)

        # 4. Vice-versa: user uploads 'future-tagger-v9' first, then a future app update adds 'future-tagger-v9' as built-in
        resp_future = await upload_custom_model(
            files=[
                make_upload_file("future-tagger-v9.onnx", onnx_bytes),
                make_upload_file("selected_tags.csv", csv_bytes),
            ],
            name="",
            current_user=self.admin_user,
        )
        future_custom_id = resp_future["model"]["id"]
        self.assertEqual(future_custom_id, "custom:future-tagger-v9")

        await update_settings(
            WDTaggerSettingsRequest(model_name=future_custom_id),
            current_user=self.admin_user,
        )

        # Simulate future update adding 'future-tagger-v9' to AVAILABLE_MODELS & BUILTIN_MODEL_CONFIGS
        WDTagger.AVAILABLE_MODELS["future-tagger-v9"] = "SomeOrg/future-tagger-v9"
        BUILTIN_MODEL_CONFIGS["future-tagger-v9"] = ModelInferenceConfig(input_size=448)
        try:
            all_models = await get_models(current_user=self.admin_user)
            by_id = {m["id"]: m for m in all_models}
            self.assertIn("future-tagger-v9", by_id)
            self.assertFalse(by_id["future-tagger-v9"]["is_custom"])
            self.assertIn("custom:future-tagger-v9", by_id)
            self.assertTrue(by_id["custom:future-tagger-v9"]["is_custom"])

            # Custom model remains downloaded and runnable while new built-in is not yet downloaded
            custom_status = await get_model_status("custom:future-tagger-v9", current_user=self.admin_user)
            builtin_status = await get_model_status("future-tagger-v9", current_user=self.admin_user)
            self.assertTrue(custom_status.is_downloaded)
            self.assertFalse(builtin_status.is_downloaded)
        finally:
            WDTagger.AVAILABLE_MODELS.pop("future-tagger-v9", None)
            BUILTIN_MODEL_CONFIGS.pop("future-tagger-v9", None)

    async def test_multifile_external_weights_upload_test_predict_and_uninstall(self):
        # Build NCHW fixed-batch-1 model with external weights file 'model.onnx.data' outputting logits
        onnx_bytes, ext_bytes = build_synthetic_onnx(
            [3.0, -3.0, 2.5],
            input_size=64,
            nchw=True,
            fixed_batch_one=True,
            external_data_filename="model.onnx.data",
        )
        tags_json = json.dumps({
            "categories": [
                {"name": "general", "offset": 0, "count": 2, "tags": ["monochrome", "sketch"]},
                {"name": "character", "offset": 2, "count": 1, "tags": ["hatsune_miku"]},
            ]
        }).encode("utf-8")

        resp = await upload_custom_model(
            files=[
                make_upload_file("model.onnx", onnx_bytes),
                make_upload_file("model.onnx.data", ext_bytes),
                make_upload_file("tags.json", tags_json),
            ],
            name="External Weights Tagger",
            current_user=self.admin_user,
        )
        custom_id = resp["model"]["id"]
        self.assertEqual(custom_id, "custom:external-weights-tagger")
        self.assertTrue(resp["model"]["fixed_batch_one"])
        self.assertEqual(resp["model"]["default_config"]["input_layout"], "nchw")
        self.assertEqual(resp["model"]["default_config"]["output_activation"], "sigmoid")

        # Save settings with conservative thresholds
        await update_settings(
            WDTaggerSettingsRequest(
                model_name=custom_id,
                general_threshold=0.5,
                character_threshold=0.99,
            ),
            current_user=self.admin_user,
        )

        # Test Model endpoint uses LIVE unsaved inputs (clamped to min/max) on no-thumbnail.png
        test_res = await test_model(
            TestModelRequest(
                model_name=custom_id,
                general_threshold=-5.0,       # clamps to 0.0
                character_threshold=0.80,     # overrides saved 0.99 without saving!
                blacklisted_tags=["sketch"],  # transient blacklist
                inference_config={
                    "batch_size": 500,        # clamps to 64 (and warns about fixed_batch_one)
                    "temperature": 0.001,     # clamps to 0.05
                    "input_size": 64,
                },
            ),
            current_user=self.admin_user,
            db=self.db,
        )
        self.assertTrue(test_res["success"])
        self.assertEqual(test_res["effective_settings"]["general_threshold"], 0.0)
        self.assertEqual(test_res["effective_settings"]["character_threshold"], 0.8)
        self.assertEqual(test_res["effective_settings"]["inference_config"]["batch_size"], 64)
        self.assertEqual(test_res["effective_settings"]["inference_config"]["temperature"], 0.05)
        self.assertTrue(any("static batch dimension of 1" in w for w in test_res["warnings"]))

        predicted_names = [t.name for t in test_res["tags"]]
        self.assertIn("monochrome", predicted_names)
        self.assertIn("hatsune_miku", predicted_names)
        self.assertNotIn("sketch", predicted_names)

        # Verify saved settings in settings.json were NOT mutated by Test Model
        saved_after_test = await get_settings(current_user=self.admin_user)
        self.assertEqual(saved_after_test["general_threshold"], 0.5)
        self.assertEqual(saved_after_test["character_threshold"], 0.99)
        self.assertEqual(saved_after_test["blacklisted_tags"], [])

        # Predict on real media items (batch > 1 exercises fixed_batch_one loop AND preprocess executor)
        for idx in (1, 2):
            img_path = self.original_dir / f"sample_{idx}.png"
            Image.new("RGB", (96, 96), (120, 140, 160)).save(img_path)
            self.db.add(Media(
                id=idx,
                filename=f"sample_{idx}.png",
                path=str(img_path),
                file_type=FileTypeEnum.image,
                hash=f"hash_{idx}",
                file_size=1024,
                width=96,
                height=96,
                rating=RatingEnum.safe,
            ))
        self.db.commit()

        single_pred = await predict_tags(
            media_id=1,
            request=PredictTagsRequest(model_name=custom_id, general_threshold=0.5, character_threshold=0.8),
            current_user=self.admin_user,
            db=self.db,
        )
        self.assertIn("monochrome", [t.name for t in single_pred.tags])

        # Uninstall the active custom model -> removes files on disk, resets active model, keeps executor alive
        model_folder = self.custom_models_dir / "external-weights-tagger"
        self.assertTrue(model_folder.exists())

        del_res = await delete_model(custom_id, current_user=self.admin_user)
        self.assertTrue(del_res["success"])
        self.assertEqual(del_res["active_model"], "wd-eva02-large-tagger-v3")
        self.assertFalse(model_folder.exists())
        self.assertFalse(get_wd_tagger().is_loaded)

        # Upload another custom model and run batch prediction to confirm _preprocess_executor was NOT killed by delete_model
        onnx2, _ = build_synthetic_onnx([0.95, 0.1], input_size=64, nchw=False)
        resp2 = await upload_custom_model(
            files=[
                make_upload_file("second.onnx", onnx2),
                make_upload_file("tags.txt", b"landscape\nnight\n"),
            ],
            name="Second Model",
            current_user=self.admin_user,
        )
        batch_pred = await predict_tags_batch(
            request=BatchPredictRequest(
                media_ids=[1, 2],
                model_name=resp2["model"]["id"],
                general_threshold=0.5,
            ),
            current_user=self.admin_user,
            db=self.db,
        )
        self.assertEqual(len(batch_pred.results), 2)
        self.assertEqual([t.name for t in batch_pred.results[0].tags], ["landscape"])

    async def test_invalid_uploads_rejected_and_staging_cleaned(self):
        from fastapi import HTTPException

        # 1. Disallowed extension (.py)
        with self.assertRaises(HTTPException) as ctx1:
            await upload_custom_model(
                files=[make_upload_file("evil.py", b"print(1)")],
                name="Evil",
                current_user=self.admin_user,
            )
        self.assertEqual(ctx1.exception.status_code, 400)

        # 2. Missing label file
        onnx_bytes, _ = build_synthetic_onnx([0.5, 0.5], input_size=64)
        with self.assertRaises(HTTPException) as ctx2:
            await upload_custom_model(
                files=[make_upload_file("model.onnx", onnx_bytes)],
                name="No Labels",
                current_user=self.admin_user,
            )
        self.assertEqual(ctx2.exception.status_code, 400)

        # 3. Corrupted ONNX file
        with self.assertRaises(HTTPException) as ctx3:
            await upload_custom_model(
                files=[
                    make_upload_file("corrupt.onnx", b"not-an-onnx-protobuf"),
                    make_upload_file("tags.txt", b"tag1\ntag2\n"),
                ],
                name="Corrupt",
                current_user=self.admin_user,
            )
        self.assertEqual(ctx3.exception.status_code, 400)

        # Verify staging directory has zero leftover folders
        staging_root = self.custom_models_dir / ".staging"
        if staging_root.exists():
            self.assertEqual(list(staging_root.iterdir()), [])

    async def test_builtin_per_model_overrides_and_reset_cleanup(self):
        target_builtin = "wd-vit-tagger-v3"
        default_batch = BUILTIN_MODEL_CONFIGS[target_builtin].batch_size

        # Override batch_size and temperature on built-in model
        updated = await update_settings(
            WDTaggerSettingsRequest(
                model_name=target_builtin,
                inference_config={"batch_size": 32, "temperature": 1.5},
            ),
            current_user=self.admin_user,
        )
        self.assertEqual(updated["model_settings"][target_builtin]["batch_size"], 32)
        self.assertEqual(updated["model_settings"][target_builtin]["temperature"], 1.5)
        self.assertEqual(get_wd_tagger().get_optimal_batch_size(target_builtin), 32)

        # Resetting back to built-in defaults removes the override entry from model_settings
        reset_resp = await update_settings(
            WDTaggerSettingsRequest(
                model_name=target_builtin,
                inference_config=BUILTIN_MODEL_CONFIGS[target_builtin].to_dict(),
            ),
            current_user=self.admin_user,
        )
        self.assertNotIn(target_builtin, reset_resp["model_settings"])
        self.assertEqual(get_wd_tagger().get_optimal_batch_size(target_builtin), default_batch)

    async def test_config_json_parsing_animetimm_and_custom_norm(self):
        # 1. animetimm/convnextv2_huge.dbv4-full style config.json with dynamic spatial ONNX tensor
        onnx_dyn, _ = build_synthetic_onnx([2.2, -1.5, 3.0], nchw=True, dynamic_spatial=True)
        csv_bytes = (
            "tag_id,name,category,count\n"
            "1,1girl,0,100\n"
            "2,solo,0,90\n"
            "3,reimu,4,80\n"
        ).encode("utf-8")
        animetimm_cfg = json.dumps({
            "architecture": "convnextv2_huge",
            "crop_mode": "squash",
            "crop_pct": 1.0,
            "fixed_input_size": False,
            "hf_hub_id": "animetimm/convnextv2_huge.dbv4-full",
            "input_size": [3, 512, 512],
            "interpolation": "bicubic",
            "mean": [0.485, 0.456, 0.406],
            "num_classes": 3,
            "std": [0.229, 0.224, 0.225],
            "test_input_size": [3, 512, 512],
        }).encode("utf-8")

        resp = await upload_custom_model(
            files=[
                make_upload_file("model.onnx", onnx_dyn),
                make_upload_file("selected_tags.csv", csv_bytes),
                make_upload_file("config.json", animetimm_cfg),
            ],
            name="",
            current_user=self.admin_user,
        )
        self.assertTrue(resp["success"])
        self.assertEqual(resp["warnings"], [])
        model_desc = resp["model"]
        self.assertEqual(model_desc["display_name"], "convnextv2_huge.dbv4-full")
        self.assertEqual(model_desc["id"], "custom:convnextv2-huge.dbv4-full")

        cfg = model_desc["default_config"]
        self.assertEqual(cfg["input_size"], 512)
        self.assertEqual(cfg["input_layout"], "nchw")
        self.assertEqual(cfg["color_space"], "rgb")
        self.assertEqual(cfg["normalization"], "imagenet")
        self.assertEqual(cfg["interpolation"], "bicubic")
        self.assertEqual(cfg["resize_mode"], "stretch")

        # Run test endpoint against no-thumbnail.png using the config.json-derived defaults
        test_res = await test_model(
            TestModelRequest(model_name=model_desc["id"], general_threshold=0.5, character_threshold=0.8),
            current_user=self.admin_user,
            db=self.db,
        )
        self.assertTrue(test_res["success"])
        self.assertEqual(test_res["resolved_activation"], "sigmoid")
        self.assertIn("1girl", [t.name for t in test_res["tags"]])
        self.assertIn("reimu", [t.name for t in test_res["tags"]])

        # 2. Static ONNX spatial dim (64) + custom mean/std config.json (saying 512) preserves 64 and warns
        onnx_static, _ = build_synthetic_onnx([0.9, 0.1, 0.85], input_size=64, nchw=True)
        custom_cfg = json.dumps({
            "pretrained_cfg": {
                "input_size": [3, 512, 512],
                "mean": [0.4, 0.45, 0.5],
                "std": [0.2, 0.25, 0.3],
                "interpolation": "bilinear",
                "crop_mode": "border",
                "fill_color": 0,
            }
        }).encode("utf-8")

        resp2 = await upload_custom_model(
            files=[
                make_upload_file("custom_static.onnx", onnx_static),
                make_upload_file("tags.json", json.dumps(["a", "b", "c"]).encode("utf-8")),
                make_upload_file("model_meta_config.json", custom_cfg),
            ],
            name="Static With Config",
            current_user=self.admin_user,
        )
        cfg2 = resp2["model"]["default_config"]
        self.assertEqual(cfg2["input_size"], 64)
        self.assertEqual(cfg2["normalization"], "custom")
        self.assertEqual(cfg2["norm_mean"], [0.4, 0.45, 0.5])
        self.assertEqual(cfg2["norm_std"], [0.2, 0.25, 0.3])
        self.assertEqual(cfg2["resize_mode"], "pad_black")
        self.assertTrue(any("static size 64" in w for w in resp2["warnings"]))


if __name__ == "__main__":
    unittest.main()
