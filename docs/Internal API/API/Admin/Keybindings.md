## Admin: Keybindings

> [!NOTE]
> Last updated: `October 10, 2026`

**Base path:** `/api/admin`

All keybinding endpoints require `require_admin_mode`.

### Get keybindings

```
GET /api/admin/keybindings
```

Returns the full action registry (with action IDs, UI contexts, translation label keys, and default bindings) along with the active merged keybindings.

**Response:**

```json
{
  "actions": [
    {
      "id": "media_nav_prev",
      "context": "media_viewer",
      "label_key": "admin.keybindings.actions.media_nav_prev",
      "default": {
        "code": "ArrowLeft",
        "key": "ArrowLeft"
      }
    },
    {
      "id": "media_nav_next",
      "context": "media_viewer",
      "label_key": "admin.keybindings.actions.media_nav_next",
      "default": {
        "code": "ArrowRight",
        "key": "ArrowRight"
      }
    }
  ],
  "bindings": {
    "media_nav_prev": {
      "code": "ArrowLeft",
      "key": "ArrowLeft"
    },
    "media_nav_next": {
      "code": "ArrowRight",
      "key": "ArrowRight"
    }
  }
}
```

### Update keybindings

```
PUT /api/admin/keybindings
Content-Type: application/json

{
  "bindings": {
    "media_nav_prev": {
      "code": "KeyA",
      "key": "a"
    },
    "media_nav_next": {
      "code": "KeyD",
      "key": "d"
    }
  }
}
```

Updates one or more keybinding definitions and persists them to `settings.json`.

- Validates incoming keys against disallowed key codes (`Tab`, `Enter`, `NumpadEnter`, `Escape`, `CapsLock`, `ContextMenu`).
- Detects key conflicts within the same UI context (e.g. assigning the same key to two actions in `media_viewer`).

**Conflict Error (409 Conflict):**

Returned when multiple actions within the same UI context are assigned the same key code.

```json
{
  "detail": {
    "error": "conflict",
    "action": "media_nav_next",
    "conflicts_with": "media_nav_prev"
  }
}
```

**Disallowed Key Error (422 Unprocessable Entity):**

Returned when attempting to bind a prohibited key code (e.g. `Tab`, `Enter`, `NumpadEnter`, `Escape`, `CapsLock`, `ContextMenu`) or when validation fails.

```json
{
  "detail": "disallowed:Tab"
}
```

**Success Response (200 OK):**

```json
{
  "bindings": {
    "media_nav_prev": {
      "code": "KeyA",
      "key": "a"
    },
    "media_nav_next": {
      "code": "KeyD",
      "key": "d"
    }
  }
}
```

### Reset keybindings

```
POST /api/admin/keybindings/reset
Content-Type: application/json

{
  "action_id": "media_nav_prev"
}
```

Resets a single keybinding (if `action_id` is supplied) or all keybindings (if request body is empty or omitted) to built-in default values in `settings.json`.

**Response:**

```json
{
  "bindings": {
    "media_nav_prev": {
      "code": "ArrowLeft",
      "key": "ArrowLeft"
    },
    "media_nav_next": {
      "code": "ArrowRight",
      "key": "ArrowRight"
    }
  }
}
```
