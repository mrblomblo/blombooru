import asyncio
import unittest
from fastapi import HTTPException

from backend.app.auth import (generate_api_key, get_current_admin_user,
                              hash_api_key, require_admin_mode, verify_api_key,
                              verify_api_key_record)
from backend.app.database import check_and_migrate_schema
from backend.app.enums import ApiKeyPermissionEnum
from backend.app.models import ApiKey, User
from backend.app.routes.admin.api_keys import (create_api_key, list_api_keys,
                                               revoke_api_key, update_api_key)
from backend.app.schemas import ApiKeyCreate, ApiKeyUpdate
from tests.test_base import BackupTestBase

class DummyURL:
    def __init__(self, path: str):
        self.path = path

class DummyState:
    def __init__(self, key: ApiKey = None):
        self.current_api_key = key

class DummyRequest:
    def __init__(self, path: str = "/api/test", api_key_obj: ApiKey = None):
        self.url = DummyURL(path)
        self.state = DummyState(api_key_obj)
        self.cookies = {}
        self.headers = {}
        self.query_params = {}

class TestApiKeyPermissions(BackupTestBase):
    def setUp(self):
        super().setUp()
        # Create test user
        self.user = User(
            id=1,
            username="admin",
            password_hash="testpasshash"
        )
        self.db.add(self.user)
        self.db.commit()

    def test_api_key_model_and_migration(self):
        """Test default permission on model and migration behavior."""
        raw_key = generate_api_key()
        key_hash = hash_api_key(raw_key)
        key = ApiKey(
            key_hash=key_hash,
            key_prefix=raw_key[:12],
            name="Default Key",
            user_id=self.user.id
        )
        self.db.add(key)
        self.db.commit()
        self.db.refresh(key)
        self.assertEqual(key.permission, "read")

        # Run migration check
        check_and_migrate_schema(self.engine)

    def test_verify_api_key_record(self):
        """Test verifying active and inactive API keys."""
        raw_key = generate_api_key()
        key = ApiKey(
            key_hash=hash_api_key(raw_key),
            key_prefix=raw_key[:12],
            name="Test Key",
            permission="write",
            user_id=self.user.id
        )
        self.db.add(key)
        self.db.commit()

        # Active key resolves
        record = verify_api_key_record(self.db, raw_key)
        self.assertIsNotNone(record)
        self.assertEqual(record.permission, "write")
        self.assertEqual(record.user.id, self.user.id)

        # verify_api_key returns User object
        user_res = verify_api_key(self.db, raw_key)
        self.assertIsNotNone(user_res)
        self.assertEqual(user_res.id, self.user.id)

        # Inactive / revoked key returns None
        key.is_active = False
        self.db.commit()
        record_inactive = verify_api_key_record(self.db, raw_key)
        self.assertIsNone(record_inactive)
        user_inactive = verify_api_key(self.db, raw_key)
        self.assertIsNone(user_inactive)

    def test_admin_api_keys_routes(self):
        """Test creating, listing, updating, and revoking API keys via admin routes."""
        # 1. Create a key with 'read' permission
        create_data_read = ApiKeyCreate(name="Viewer Key", permission=ApiKeyPermissionEnum.read)
        res_read = asyncio.run(create_api_key(data=create_data_read, current_user=self.user, db=self.db))
        self.assertEqual(res_read["name"], "Viewer Key")
        self.assertEqual(res_read["permission"], "read")
        self.assertTrue(res_read["key"].startswith("blom_"))
        key_id = res_read["id"]

        # 2. List keys
        keys_list = asyncio.run(list_api_keys(current_user=self.user, db=self.db))
        self.assertEqual(len(keys_list), 1)
        self.assertEqual(keys_list[0].permission, "read")

        # 3. Update key permission to 'write' and rename it
        update_data = ApiKeyUpdate(name="Uploader Key", permission=ApiKeyPermissionEnum.write)
        res_update = asyncio.run(update_api_key(key_id=key_id, data=update_data, current_user=self.user, db=self.db))
        self.assertEqual(res_update.name, "Uploader Key")
        self.assertEqual(res_update.permission, "write")

        # 4. Revoke key
        res_revoke = asyncio.run(revoke_api_key(key_id=key_id, current_user=self.user, db=self.db))
        self.assertEqual(res_revoke["message_key"], "notifications.admin.api_key_revoked")

        # 5. List keys again (revoked keys are omitted from active list)
        keys_list_after = asyncio.run(list_api_keys(current_user=self.user, db=self.db))
        self.assertEqual(len(keys_list_after), 0)

    def test_require_admin_mode_permission_boundaries(self):
        """Test read, write, and admin permission boundaries in require_admin_mode."""
        # 1. Read-only key
        read_raw = generate_api_key()
        read_key = ApiKey(
            key_hash=hash_api_key(read_raw),
            key_prefix=read_raw[:12],
            name="Read Key",
            permission="read",
            user_id=self.user.id
        )
        self.db.add(read_key)

        # 2. Write key
        write_raw = generate_api_key()
        write_key = ApiKey(
            key_hash=hash_api_key(write_raw),
            key_prefix=write_raw[:12],
            name="Write Key",
            permission="write",
            user_id=self.user.id
        )
        self.db.add(write_key)

        # 3. Admin key
        admin_raw = generate_api_key()
        admin_key = ApiKey(
            key_hash=hash_api_key(admin_raw),
            key_prefix=admin_raw[:12],
            name="Admin Key",
            permission="admin",
            user_id=self.user.id
        )
        self.db.add(admin_key)
        self.db.commit()

        # Test Read key against content mutation route -> 403
        req_mutate = DummyRequest("/api/media/upload", read_key)
        with self.assertRaises(HTTPException) as ctx:
            require_admin_mode(request=req_mutate, api_key_user=self.user)
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn("read-only access", ctx.exception.detail)

        # Test Read key against admin route -> 403
        req_admin = DummyRequest("/api/admin/settings", read_key)
        with self.assertRaises(HTTPException) as ctx:
            require_admin_mode(request=req_admin, api_key_user=self.user)
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn("requires administrator access", ctx.exception.detail)

        # Test Write key against content mutation route -> Allowed
        req_mutate_write = DummyRequest("/api/media/upload", write_key)
        result = require_admin_mode(request=req_mutate_write, api_key_user=self.user)
        self.assertEqual(result.id, self.user.id)

        # Test Write key against admin route -> 403
        req_admin_write = DummyRequest("/api/admin/settings", write_key)
        with self.assertRaises(HTTPException) as ctx:
            require_admin_mode(request=req_admin_write, api_key_user=self.user)
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn("requires administrator access", ctx.exception.detail)

        # Test Admin key against content mutation route -> Allowed
        req_mutate_admin = DummyRequest("/api/media/upload", admin_key)
        result = require_admin_mode(request=req_mutate_admin, api_key_user=self.user)
        self.assertEqual(result.id, self.user.id)

        # Test Admin key against admin route -> Allowed
        req_admin_admin = DummyRequest("/api/admin/settings", admin_key)
        result = require_admin_mode(request=req_admin_admin, api_key_user=self.user)
        self.assertEqual(result.id, self.user.id)

    def test_get_current_admin_user_permission_boundaries(self):
        """Test get_current_admin_user with API key permissions."""
        read_key = ApiKey(
            key_hash=hash_api_key("blom_read"),
            key_prefix="blom_read12",
            name="Read Key",
            permission="read",
            user_id=self.user.id
        )
        write_key = ApiKey(
            key_hash=hash_api_key("blom_write"),
            key_prefix="blom_writ12",
            name="Write Key",
            permission="write",
            user_id=self.user.id
        )
        admin_key = ApiKey(
            key_hash=hash_api_key("blom_admin"),
            key_prefix="blom_admi12",
            name="Admin Key",
            permission="admin",
            user_id=self.user.id
        )
        self.db.add_all([read_key, write_key, admin_key])
        self.db.commit()

        # Read key on non-admin route -> 403
        req1 = DummyRequest("/api/media/1/tags", read_key)
        with self.assertRaises(HTTPException) as ctx:
            get_current_admin_user(request=req1, api_key_user=self.user)
        self.assertEqual(ctx.exception.status_code, 403)

        # Write key on non-admin route -> allowed
        req2 = DummyRequest("/api/media/1/tags", write_key)
        res2 = get_current_admin_user(request=req2, api_key_user=self.user)
        self.assertEqual(res2.id, self.user.id)

        # Write key on /api/admin route -> 403
        req3 = DummyRequest("/api/admin/backup/export", write_key)
        with self.assertRaises(HTTPException) as ctx:
            get_current_admin_user(request=req3, api_key_user=self.user)
        self.assertEqual(ctx.exception.status_code, 403)

        # Admin key on /api/admin route -> allowed
        req4 = DummyRequest("/api/admin/backup/export", admin_key)
        res4 = get_current_admin_user(request=req4, api_key_user=self.user)
        self.assertEqual(res4.id, self.user.id)

    def test_api_key_name_max_length(self):
        """Test that API key names longer than 64 characters are rejected."""
        valid_name_64 = "a" * 64
        invalid_name_65 = "a" * 65

        # 64 chars is valid
        create_valid = ApiKeyCreate(name=valid_name_64, permission=ApiKeyPermissionEnum.read)
        self.assertEqual(create_valid.name, valid_name_64)

        update_valid = ApiKeyUpdate(name=valid_name_64)
        self.assertEqual(update_valid.name, valid_name_64)

        # >64 chars fails validation
        with self.assertRaises(Exception):
            ApiKeyCreate(name=invalid_name_65, permission=ApiKeyPermissionEnum.read)

        with self.assertRaises(Exception):
            ApiKeyUpdate(name=invalid_name_65)

    def test_real_schema_migration(self):
        """Test that migration actually adds 'permission' with default 'admin' to existing records."""
        from sqlalchemy import create_engine, inspect, text
        from backend.app.database import migrate_add_api_key_permission

        temp_engine = create_engine("sqlite:///:memory:")
        with temp_engine.connect() as conn:
            conn.execute(text("""
                CREATE TABLE blombooru_api_keys (
                    id INTEGER PRIMARY KEY,
                    key_hash VARCHAR(64) NOT NULL,
                    key_prefix VARCHAR(12) NOT NULL,
                    name VARCHAR(64),
                    user_id INTEGER NOT NULL
                )
            """))
            conn.execute(text("""
                INSERT INTO blombooru_api_keys (key_hash, key_prefix, name, user_id)
                VALUES ('testhash', 'blom_test12', 'Old Key', 1)
            """))
            conn.commit()

        # Run migration on engine with old schema
        inspector = inspect(temp_engine)
        migrate_add_api_key_permission(temp_engine, inspector)

        # Verify column and default value on existing record
        with temp_engine.connect() as conn:
            row = conn.execute(text("SELECT id, name, permission FROM blombooru_api_keys WHERE id = 1")).fetchone()
            self.assertEqual(row[1], "Old Key")
            self.assertEqual(row[2], "admin")

        temp_engine.dispose()

    def test_key_presentation_formats_and_positive_read_auth(self):
        """Test Bearer, bare, basic auth, and query parameter key presentations."""
        import base64
        from backend.app.auth import get_current_user_from_api_key

        read_raw = generate_api_key()
        read_key = ApiKey(
            key_hash=hash_api_key(read_raw),
            key_prefix=read_raw[:12],
            name="Read-Only Key",
            permission="read",
            user_id=self.user.id
        )
        self.db.add(read_key)
        self.db.commit()

        # 1. Bearer format: "Bearer blom_..."
        req_bearer = DummyRequest("/api/media/search")
        req_bearer.headers["Authorization"] = f"Bearer {read_raw}"
        resolved_user = get_current_user_from_api_key(req_bearer, self.db)
        self.assertIsNotNone(resolved_user)
        self.assertEqual(resolved_user.id, self.user.id)
        self.assertEqual(req_bearer.state.current_api_key.permission, "read")

        # 2. Bare format: "blom_..."
        req_bare = DummyRequest("/api/tags")
        req_bare.headers["Authorization"] = read_raw
        resolved_user2 = get_current_user_from_api_key(req_bare, self.db)
        self.assertIsNotNone(resolved_user2)
        self.assertEqual(resolved_user2.id, self.user.id)

        # 3. Basic auth: "Basic base64(admin:blom_...)"
        basic_creds = base64.b64encode(f"admin:{read_raw}".encode()).decode()
        req_basic = DummyRequest("/danbooru/posts.json")
        req_basic.headers["Authorization"] = f"Basic {basic_creds}"
        resolved_user3 = get_current_user_from_api_key(req_basic, self.db)
        self.assertIsNotNone(resolved_user3)
        self.assertEqual(resolved_user3.id, self.user.id)

        # 4. Query param: "?api_key=blom_..."
        req_query = DummyRequest("/api/media/1")
        req_query.query_params["api_key"] = read_raw
        resolved_user4 = get_current_user_from_api_key(req_query, self.db)
        self.assertIsNotNone(resolved_user4)
        self.assertEqual(resolved_user4.id, self.user.id)

    def test_browser_session_and_admin_mode_toggle(self):
        """Test browser cookie session auth and the admin_mode UI safety toggle."""
        # 1. Cookie session with admin_mode active -> allowed
        req_cookie_active = DummyRequest("/api/media/delete")
        req_cookie_active.cookies["admin_token"] = "valid_jwt"
        res1 = require_admin_mode(request=req_cookie_active, current_user=self.user, admin_mode_active=True, api_key_user=None)
        self.assertEqual(res1.id, self.user.id)

        # 2. Cookie session with admin_mode inactive -> 403
        req_cookie_inactive = DummyRequest("/api/media/delete")
        req_cookie_inactive.cookies["admin_token"] = "valid_jwt"
        with self.assertRaises(HTTPException) as ctx:
            require_admin_mode(request=req_cookie_inactive, current_user=self.user, admin_mode_active=False, api_key_user=None)
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn("logged in as the admin", ctx.exception.detail)

        # 3. Non-cookie bearer session (API JWT) -> allowed even if admin_mode_active is False
        req_bearer_jwt = DummyRequest("/api/media/delete")
        res3 = require_admin_mode(request=req_bearer_jwt, current_user=self.user, admin_mode_active=False, api_key_user=None)
        self.assertEqual(res3.id, self.user.id)

        # 4. Unauthenticated -> 401
        req_anon = DummyRequest("/api/media/delete")
        with self.assertRaises(HTTPException) as ctx4:
            require_admin_mode(request=req_anon, current_user=None, admin_mode_active=False, api_key_user=None)
        self.assertEqual(ctx4.exception.status_code, 401)

    def test_fail_closed_permission_enforcement(self):
        """Test that missing or unknown permission on an API key fails closed to read-only."""
        from backend.app.auth import _enforce_api_key_permission

        # Empty state / no API key attached -> defaults to 'read' (fails on write route)
        req_empty = DummyRequest("/api/media/upload", None)
        with self.assertRaises(HTTPException) as ctx:
            _enforce_api_key_permission(req_empty, self.user)
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn("read-only access", ctx.exception.detail)

        # API key object with unknown permission string -> fails closed to 403
        dummy_key = ApiKey(key_hash="hash", key_prefix="blom_123456", permission="unknown", user_id=self.user.id)
        req_unknown = DummyRequest("/api/media/upload", dummy_key)
        with self.assertRaises(HTTPException) as ctx2:
            _enforce_api_key_permission(req_unknown, self.user)
        self.assertEqual(ctx2.exception.status_code, 403)

if __name__ == "__main__":
    unittest.main()
