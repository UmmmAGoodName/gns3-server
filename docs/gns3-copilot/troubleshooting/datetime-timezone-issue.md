# Datetime Timezone Issue

## Problem Description

The API returns datetime strings without timezone suffixes, causing frontend JavaScript to parse them as local time instead of UTC time.

### Example

| Aspect | Value |
|--------|-------|
| Actual time (Beijing) | 2026-03-07 01:30 |
| Backend returns | `2026-03-06T16:31:36.547762` (no timezone) |
| Frontend displays | March 6, 16:31 |
| Should display | March 7, 00:31 (UTC 16:31 + 8 hours) |

### Root Cause

- Backend stores UTC time in database as naive datetime (no timezone info)
- FastAPI's `jsonable_encoder` serializes datetime as ISO 8601 **without timezone suffix**
- JavaScript `new Date()` treats strings without 'Z' or timezone offset as **local time**

```
Backend intention: 2026-03-06T16:31:36Z (UTC)
Actually returned: 2026-03-06T16:31:36.547762 (no timezone)
JavaScript parses as: local time 16:31
Should be: UTC 16:31 → Beijing time 00:31 (next day)
```

---

## Frontend Solutions

### Solution 1: Use dayjs UTC Parsing (Recommended)

```typescript
import dayjs from 'dayjs';
import utc from 'dayjs/plugin/utc';
import timezone from 'dayjs/plugin/timezone';

dayjs.extend(utc);
dayjs.extend(timezone);

// Parse naive datetime as UTC
const createdAt = '2026-03-06T16:31:36.547762';
const date = dayjs.utc(createdAt).tz('Asia/Shanghai');
console.log(date.format('YYYY-MM-DD HH:mm')); // 2026-03-07 00:31
```

### Solution 2: Add 'Z' Suffix Manually

```typescript
// Utility function to normalize API dates
function parseAPIDate(dateStr: string): Date {
  // Add 'Z' suffix if no timezone info present
  const normalized = dateStr.includes('Z') || dateStr.includes('+')
    ? dateStr
    : `${dateStr}Z`;
  return new Date(normalized);
}

// Usage
const date = parseAPIDate('2026-03-06T16:31:36.547762');
console.log(date.toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' }));
```

### Solution 3: Global Axios Interceptor (Most Thorough)

```typescript
import axios from 'axios';

api.interceptors.response.use((response) => {
  // Recursively normalize all date fields
  function normalizeDates(obj: any): any {
    // Match ISO 8601 datetime pattern without timezone
    if (typeof obj === 'string' && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}/.test(obj)) {
      return obj.includes('Z') || obj.includes('+') ? obj : `${obj}Z`;
    }
    if (Array.isArray(obj)) {
      return obj.map(normalizeDates);
    }
    if (obj && typeof obj === 'object') {
      return Object.fromEntries(
        Object.entries(obj).map(([k, v]) => [k, normalizeDates(v)])
      );
    }
    return obj;
  }

  response.data = normalizeDates(response.data);
  return response;
});
```

---

## Backend Context

### Current Implementation

**File**: `gns3server/api/server.py:58-64`

```python
application = FastAPI(
    title="GNS3 controller API",
    description="This page describes the public controller API for GNS3",
    version="v3",
    docs_url=None,
    redoc_url=None
)
```

**File**: `gns3server/db/models/base.py`

```python
from fastapi.encoders import jsonable_encoder

class Base:
    def asjson(self):
        return jsonable_encoder(self.asdict())
```

### Datetime Flow

1. Database stores naive datetime (no timezone)
2. FastAPI uses `jsonable_encoder` to serialize
3. Output format: `YYYY-MM-DDTHH:MM:SS.ffffff` (no 'Z' suffix)
4. JavaScript interprets as local time

### Affected Fields

- `created_at`
- `updated_at`
- `last_login`
- Any other datetime fields in API responses

---

## Testing Checklist

- [ ] Verify datetime displays correctly in Beijing timezone (UTC+8)
- [ ] Test with other timezones (e.g., UTC-5, UTC+0)
- [ ] Check daylight saving time transitions (if applicable)
- [ ] Verify datetime input/insertion still works correctly

---

## Related Files

- Backend: `gns3server/api/server.py`
- Backend: `gns3server/db/models/base.py`
- Schemas: `gns3server/schemas/controller/base.py`


---

## License

**Copyright © 2025 Yue Guobin (岳国宾)**

This work is licensed under the [Creative Commons Attribution-ShareAlike 4.0
International License (CC BY-SA 4.0)](https://creativecommons.org/licenses/by-sa/4.0/).

![CC BY-SA 4.0](https://i.creativecommons.org/l/by-sa/4.0/88x31.png)

### Summary

You are free to:

- **Share** — Copy and redistribute the material in any medium or format
- **Adapt** — Remix, transform, and build upon the material for any purpose

Under the following terms:

- **Attribution** — You must give appropriate credit to **Yue Guobin (岳国宾)**, provide
  a link to the license, and indicate if changes were made.
- **ShareAlike** — If you remix, transform, or build upon the material, you must
  distribute your contributions under the **same license** (CC BY-SA 4.0).

Full license text: [DESIGN_DOCS_LICENSE](../DESIGN_DOCS_LICENSE.md)

