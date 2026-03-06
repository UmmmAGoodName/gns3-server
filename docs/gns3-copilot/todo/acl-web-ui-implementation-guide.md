# ACL Web UI Implementation Guide

**Document Status**: Design Phase
**Priority**: High
**Created**: 2026-03-06
**Target Audience**: Frontend Developers

---

## Table of Contents

- [Feature Overview](#feature-overview)
- [API Endpoints Details](#api-endpoints-details)
- [Data Structures](#data-structures)
- [Frontend Implementation Guide](#frontend-implementation-guide)
- [UI/UX Design Recommendations](#uiux-design-recommendations)
- [Common Scenarios](#common-scenarios)
- [Error Handling](#error-handling)
- [Example Code](#example-code)

---

## Feature Overview

### Objective

Implement ACL (Access Control List) management functionality in the GNS3 Web UI, allowing administrators to manage user permissions through a graphical interface.

### Core Features

1. **View ACL List** - Display all ACEs (Access Control Entries)
2. **Create ACE** - Add new access control entries
3. **Edit ACE** - Modify existing ACE properties
4. **Delete ACE** - Remove unwanted access control entries
5. **Get Available Endpoints** - Retrieve list of resources that can be configured with ACL

### User Flow

```
Administrator Login
    ↓
Navigate to "Permission Management" page
    ↓
View existing ACL list
    ↓
Select action:
  - Create new ACE → Fill form → Submit
  - Edit existing ACE → Modify form → Save
  - Delete ACE → Confirm → Delete
```

---

## API Endpoints Details

### Base URL

```
http://localhost:3080/v3/access/aces
```

### 1. Get All ACEs

**Endpoint**: `GET /v3/access/aces`

**Privilege**: `ACE.Audit`

**Request Example**:
```javascript
const response = await fetch('/v3/access/aces', {
  headers: {
    'Authorization': `Bearer ${token}`
  }
});
const aces = await response.json();
```

**Response Example**:
```json
[
  {
    "ace_id": "550e8400-e29b-41d4-a716-446655440000",
    "path": "/projects",
    "user_id": "650e8400-e29b-41d4-a716-446655440001",
    "group_id": null,
    "role_id": "750e8400-e29b-41d4-a716-446655440002",
    "allowed": true,
    "propagate": true,
    "ace_type": "user",
    "created_at": "2026-03-06T10:00:00Z",
    "updated_at": "2026-03-06T10:00:00Z"
  }
]
```

---

### 2. Get Single ACE

**Endpoint**: `GET /v3/access/aces/{ace_id}`

**Privilege**: `ACE.Audit`

**Request Example**:
```javascript
const response = await fetch(`/v3/access/aces/${aceId}`, {
  headers: {
    'Authorization': `Bearer ${token}`
  }
});
const ace = await response.json();
```

---

### 3. Create ACE

**Endpoint**: `POST /v3/access/aces`

**Privilege**: `ACE.Allocate`

**Request Example**:
```javascript
const newAce = {
  path: "/projects",
  user_id: "550e8400-e29b-41d4-a716-446655440000",
  role_id: "750e8400-e29b-41d4-a716-446655440002",
  allowed: true,
  propagate: true
};

const response = await fetch('/v3/access/aces', {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${token}`,
    'Content-Type': 'application/json'
  },
  body: JSON.stringify(newAce)
});
const createdAce = await response.json();
```

**Response**: `201 Created` + Created ACE object

---

### 4. Update ACE ⭐ Core Feature

**Endpoint**: `PUT /v3/access/aces/{ace_id}`

**Privilege**: `ACE.Modify`

**Request Example**:
```javascript
const updatedAce = {
  path: "/projects/updated",
  allowed: false,
  propagate: false
};

const response = await fetch(`/v3/access/aces/${aceId}`, {
  method: 'PUT',
  headers: {
    'Authorization': `Bearer ${token}`,
    'Content-Type': 'application/json'
  },
  body: JSON.stringify(updatedAce)
});
const updated = await response.json();
```

**Important**:
- Supports **partial updates** - only submit fields to modify
- `user_id` and `group_id` cannot both be present (choose one)
- `path` must match an existing API endpoint

---

### 5. Delete ACE

**Endpoint**: `DELETE /v3/access/aces/{ace_id}`

**Privilege**: `ACE.Allocate`

**Request Example**:
```javascript
const response = await fetch(`/v3/access/aces/${aceId}`, {
  method: 'DELETE',
  headers: {
    'Authorization': `Bearer ${token}`
  }
});
// Response: 204 No Content
```

---

### 6. Get Available Endpoints (for Path Selection)

**Endpoint**: `GET /v3/access/aces/endpoints`

**Privilege**: `ACE.Audit`

**Request Example**:
```javascript
const response = await fetch('/v3/access/aces/endpoints', {
  headers: {
    'Authorization': `Bearer ${token}`
  }
});
const endpoints = await response.json();
```

**Response Example**:
```json
[
  {
    "endpoint": "/",
    "name": "All endpoints",
    "endpoint_type": "root"
  },
  {
    "endpoint": "/projects",
    "name": "All projects",
    "endpoint_type": "project"
  },
  {
    "endpoint": "/projects/123e4567-e89b-12d3-a456-426614174000",
    "name": "Project \"My Project\"",
    "endpoint_type": "project"
  },
  {
    "endpoint": "/projects/123e4567-e89b-12d3-a456-426614174000/nodes",
    "name": "All nodes in project \"My Project\"",
    "endpoint_type": "node"
  },
  {
    "endpoint": "/pools",
    "name": "All resource pools",
    "endpoint_type": "pool"
  }
]
```

---

### 7. Get Related Data

#### Get Users List

**Endpoint**: `GET /v3/access/users`

**Privilege**: `User.Audit`

```javascript
const response = await fetch('/v3/access/users', {
  headers: { 'Authorization': `Bearer ${token}` }
});
const users = await response.json();
```

#### Get User Groups List

**Endpoint**: `GET /v3/access/groups`

**Privilege**: `Group.Audit`

```javascript
const response = await fetch('/v3/access/groups', {
  headers: { 'Authorization': `Bearer ${token}` }
});
const groups = await response.json();
```

#### Get Roles List

**Endpoint**: `GET /v3/access/roles`

**Privilege**: `Role.Audit`

```javascript
const response = await fetch('/v3/access/roles', {
  headers: { 'Authorization': `Bearer ${token}` }
});
const roles = await response.json();
```

---

## Data Structures

### ACE Object

```typescript
interface ACE {
  ace_id: string;           // UUID
  path: string;             // Resource path, e.g., "/projects"
  user_id?: string;         // User ID (choose one with group_id)
  group_id?: string;        // User group ID (choose one with user_id)
  role_id: string;          // Role ID
  allowed: boolean;         // Whether allowed (default true)
  propagate: boolean;       // Whether to propagate to child paths (default true)
  ace_type: "user" | "group"; // "user" or "group"
  created_at: string;       // ISO 8601 timestamp
  updated_at: string;       // ISO 8601 timestamp
}
```

### ACECreate (Creating ACE)

```typescript
interface ACECreate {
  path: string;
  user_id?: string;
  group_id?: string;
  role_id: string;
  allowed?: boolean;
  propagate?: boolean;
}
```

### ACEUpdate (Updating ACE)

```typescript
interface ACEUpdate {
  path?: string;
  user_id?: string;
  group_id?: string;
  role_id?: string;
  allowed?: boolean;
  propagate?: boolean;
}
```

### Endpoint Object

```typescript
interface Endpoint {
  endpoint: string;         // Endpoint path
  name: string;             // Display name
  endpoint_type: string;    // "root" | "project" | "node" | "link" | "user" | "group" | "role" | "pool"
}
```

---

## Frontend Implementation Guide

### Recommended Tech Stack

- **Framework**: React / Vue / Angular
- **State Management**: Redux / Vuex / NgRx
- **UI Components**: Material-UI / Ant Design / Element Plus
- **HTTP Client**: Axios / Fetch API

### Core Component Design

#### 1. ACE List Component

```
<ACLList />
  ├── <ACLFilter />      # Filter
  ├── <ACETable />       # ACE table
  │     ├── <ACERow />
  │     ├── <ACERow />
  │     └── ...
  └── <ACLCreateButton /> # Create button
```

#### 2. ACE Form Component (Create/Edit)

```
<ACEForm mode="create" />  # or mode="edit"
  ├── <PathSelector />     # Path selector
  ├── <UserGroupSelector /> # User/group selector
  ├── <RoleSelector />     # Role selector
  ├── <AllowedToggle />    # Allow/deny toggle
  ├── <PropagateToggle />  # Propagate switch
  └── <SubmitButton />
```

#### 3. Endpoint Selector Component

```
<PathSelector />
  ├── <EndpointTree />     # Tree structure showing endpoints
  │    ├── <ProjectNode />
  │    ├── <NodeNode />
  │    └── ...
  └── <EndpointSearch />   # Search box
```

---

### State Management

```typescript
// Redux example
interface ACLState {
  aces: ACE[];
  endpoints: Endpoint[];
  users: User[];
  groups: Group[];
  roles: Role[];
  loading: boolean;
  error: string | null;
}

// Actions
const loadACEs = () => async (dispatch) => {
  dispatch({ type: 'ACL_LOAD_START' });
  try {
    const aces = await api.getACEs();
    dispatch({ type: 'ACL_LOAD_SUCCESS', payload: aces });
  } catch (error) {
    dispatch({ type: 'ACL_LOAD_ERROR', payload: error.message });
  }
};

const createACE = (ace: ACECreate) => async (dispatch) => {
  const newAce = await api.createACE(ace);
  dispatch({ type: 'ACL_CREATE_SUCCESS', payload: newAce });
};

const updateACE = (aceId: string, updates: ACEUpdate) => async (dispatch) => {
  const updated = await api.updateACE(aceId, updates);
  dispatch({ type: 'ACL_UPDATE_SUCCESS', payload: updated });
};

const deleteACE = (aceId: string) => async (dispatch) => {
  await api.deleteACE(aceId);
  dispatch({ type: 'ACL_DELETE_SUCCESS', payload: aceId });
};
```

---

## UI/UX Design Recommendations

### 1. List Page Layout

```
┌─────────────────────────────────────────────────────────┐
│  Permission Management                     [New ACE]     │
├─────────────────────────────────────────────────────────┤
│  Filters: [User/Group] [Role] [Path Type] [Status]      │
├─────────────────────────────────────────────────────────┤
│  ┌───────────────────────────────────────────────────┐ │
│  │ Path          │ User/Group │ Role  │ Allow │ Action│ │
│  ├───────────────────────────────────────────────────┤ │
│  │ /projects     │ user1      │ User   │ ✓    │ Edit  │ │
│  │ /projects/123 │ group1     │ Auditor│ ✓    │ Edit  │ │
│  │ /pools/456    │ user2      │ User   │ ✗    │ Edit  │ │
│  └───────────────────────────────────────────────────┘ │
│                                         [Load More]     │
└─────────────────────────────────────────────────────────┘
```

### 2. Create/Edit Form

```
┌────────────────────────────────────────────┐
│  New Access Control Entry (ACE)    [Cancel]│
├────────────────────────────────────────────┤
│                                            │
│  Resource Path *                            │
│  ┌──────────────────────────────────────┐ │
│  │ ▼ Select Endpoint              [Search]│ │
│  └──────────────────────────────────────┘ │
│  Hint: Select the resource path to control │
│                                            │
│  Apply To *                                 │
│  ○ User  □ User Group                      │
│  ┌──────────────────────────────────────┐ │
│  │ ▼ Select User                          │ │
│  └──────────────────────────────────────┘ │
│                                            │
│  Role *                                    │
│  ┌──────────────────────────────────────┐ │
│  │ User                               ▼ │ │
│  └──────────────────────────────────────┘ │
│  Note: This role includes Project.Audit    │
│        and other privileges                │
│                                            │
│  Permission Settings                       │
│  ○ Allow Access  ● Deny Access             │
│                                            │
│  □ Propagate to Child Paths                │
│  Note: When checked, permission applies    │
│        to all child resources              │
│                                            │
│           [Cancel]              [Save]     │
└────────────────────────────────────────────┘
```

### 3. Endpoint Selector (Tree Structure)

```
┌────────────────────────────────────────────┐
│  Select Resource Path             [Search]  │
├────────────────────────────────────────────┤
│  📁 / (All endpoints)                       │
│    📁 /projects (All projects)              │
│      📁 My Project                          │
│        📁 /nodes (All nodes)                │
│          📄 Router1                         │
│          📄 Switch1                         │
│        📁 /links (All links)                │
│    📁 /pools (All resource pools)          │
│      📄 Production Pool                     │
│    📁 /templates (All templates)            │
└────────────────────────────────────────────┘
```

### 4. Interaction Design Points

#### Loading States
```javascript
// Show skeleton screen
<ACESkeleton />

// Or progress bar
<LinearProgress />
```

#### Error Messages
```javascript
// Form validation error
<FormHelperText error={true}>
  Path cannot be empty
</FormHelperText>

// API error
<Snackbar
  open={true}
  message="Creation failed: Path does not match any endpoint"
  severity="error"
/>
```

#### Confirmation Dialog
```javascript
// Delete confirmation
<Dialog>
  <DialogTitle>Confirm Delete</DialogTitle>
  <DialogContent>
    Are you sure you want to delete this ACE? This action cannot be undone.
  </DialogContent>
  <DialogActions>
    <Button onClick={cancel}>Cancel</Button>
    <Button onClick={confirm} color="error">Delete</Button>
  </DialogActions>
</Dialog>
```

---

## Common Scenarios

### Scenario 1: Create User-Level ACE

```javascript
async function createUserACE() {
  const newAce = {
    path: "/projects",
    user_id: selectedUserId,
    role_id: userRoleId,
    allowed: true,
    propagate: true
  };

  try {
    const ace = await api.createACE(newAce);
    showSuccess('ACE created successfully');
    loadACEList(); // Refresh list
  } catch (error) {
    showError(`Creation failed: ${error.message}`);
  }
}
```

### Scenario 2: Create Group-Level ACE

```javascript
async function createGroupACE() {
  const newAce = {
    path: "/templates",
    group_id: usersGroupId,
    role_id: userRoleId,
    allowed: true,
    propagate: false
  };

  try {
    const ace = await api.createACE(newAce);
    showSuccess('Group ACE created successfully');
    loadACEList();
  } catch (error) {
    showError(`Creation failed: ${error.message}`);
  }
}
```

### Scenario 3: Edit Existing ACE

```javascript
async function editACE(aceId, updates) {
  try {
    const updated = await api.updateACE(aceId, updates);
    showSuccess('ACE updated successfully');
    loadACEList();
  } catch (error) {
    showError(`Update failed: ${error.message}`);
  }
}

// Example: Toggle allowed status
async function toggleAllowed(ace) {
  await editACE(ace.ace_id, {
    allowed: !ace.allowed
  });
}

// Example: Change path
async function changePath(aceId, newPath) {
  await editACE(aceId, {
    path: newPath
  });
}
```

### Scenario 4: Delete ACE

```javascript
async function deleteACE(aceId) {
  if (!confirm('Are you sure you want to delete this ACE?')) {
    return;
  }

  try {
    await api.deleteACE(aceId);
    showSuccess('ACE deleted successfully');
    loadACEList();
  } catch (error) {
    showError(`Deletion failed: ${error.message}`);
  }
}
```

### Scenario 5: Batch Operations

```javascript
// Batch delete
async function batchDelete(aceIds) {
  const promises = aceIds.map(id => api.deleteACE(id));
  await Promise.all(promises);
  showSuccess(`Deleted ${aceIds.length} ACEs`);
  loadACEList();
}

// Batch toggle allowed status
async function batchToggleAllowed(aceIds, allowed) {
  const promises = aceIds.map(id =>
    api.updateACE(id, { allowed })
  );
  await Promise.all(promises);
  showSuccess(`Updated ${aceIds.length} ACEs`);
  loadACEList();
}
```

---

## Error Handling

### Common Error Types

| HTTP Status | Error Description | Handling |
|-------------|-------------------|----------|
| 400 Bad Request | Path doesn't match any endpoint | Prompt user to select valid path |
| 400 Bad Request | Both user_id and group_id present | Prompt user to choose one |
| 403 Forbidden | Insufficient privileges | Prompt user to contact administrator |
| 404 Not Found | ACE doesn't exist | Refresh list, notify resource deleted |
| 422 Unprocessable Entity | Validation failed | Display specific field errors |

### Error Handling Example

```javascript
async function handleAPICall(apiFunction) {
  try {
    const result = await apiFunction();
    return { success: true, data: result };
  } catch (error) {
    if (error.response) {
      const { status, data } = error.response;

      switch (status) {
        case 400:
          return {
            success: false,
            error: data.detail || 'Invalid request parameters'
          };

        case 403:
          return {
            success: false,
            error: 'Insufficient privileges, please contact administrator'
          };

        case 404:
          return {
            success: false,
            error: 'Resource not found, may have been deleted'
          };

        case 422:
          return {
            success: false,
            error: formatValidationError(data.detail)
          };

        default:
          return {
            success: false,
            error: 'Unknown error, please try again later'
          };
      }
    }

    return {
      success: false,
      error: 'Network error, please check connection'
    };
  }
}

function formatValidationError(errors) {
  // Format validation error messages
  return errors.map(err => err.msg).join(', ');
}
```

---

## Example Code

### Complete React Component Example

```jsx
import React, { useState, useEffect } from 'react';
import {
  Table,
  Button,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Select,
  MenuItem,
  Switch,
  FormControlLabel,
  TextField,
  IconButton
} from '@mui/material';
import { Edit, Delete, Add } from '@mui/icons-material';

// API Client
const api = {
  async getACEs(token) {
    const res = await fetch('/v3/access/aces', {
      headers: { 'Authorization': `Bearer ${token}` }
    });
    if (!res.ok) throw new Error(res.statusText);
    return res.json();
  },

  async getEndpoints(token) {
    const res = await fetch('/v3/access/aces/endpoints', {
      headers: { 'Authorization': `Bearer ${token}` }
    });
    if (!res.ok) throw new Error(res.statusText);
    return res.json();
  },

  async getUsers(token) {
    const res = await fetch('/v3/access/users', {
      headers: { 'Authorization': `Bearer ${token}` }
    });
    if (!res.ok) throw new Error(res.statusText);
    return res.json();
  },

  async getGroups(token) {
    const res = await fetch('/v3/access/groups', {
      headers: { 'Authorization': `Bearer ${token}` }
    });
    if (!res.ok) throw new Error(res.statusText);
    return res.json();
  },

  async getRoles(token) {
    const res = await fetch('/v3/access/roles', {
      headers: { 'Authorization': `Bearer ${token}` }
    });
    if (!res.ok) throw new Error(res.statusText);
    return res.json();
  },

  async createACE(token, data) {
    const res = await fetch('/v3/access/aces', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(data)
    });
    if (!res.ok) {
      const error = await res.json();
      throw new Error(error.detail || 'Creation failed');
    }
    return res.json();
  },

  async updateACE(token, aceId, data) {
    const res = await fetch(`/v3/access/aces/${aceId}`, {
      method: 'PUT',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(data)
    });
    if (!res.ok) {
      const error = await res.json();
      throw new Error(error.detail || 'Update failed');
    }
    return res.json();
  },

  async deleteACE(token, aceId) {
    const res = await fetch(`/v3/access/aces/${aceId}`, {
      method: 'DELETE',
      headers: { 'Authorization': `Bearer ${token}` }
    });
    if (!res.ok) throw new Error('Deletion failed');
  }
};

// ACE Form Component
function ACEForm({ token, ace, onSave, onCancel }) {
  const [endpoints, setEndpoints] = useState([]);
  const [users, setUsers] = useState([]);
  const [groups, setGroups] = useState([]);
  const [roles, setRoles] = useState([]);
  const [formData, setFormData] = useState({
    path: ace?.path || '',
    user_id: ace?.user_id || '',
    group_id: ace?.group_id || '',
    role_id: ace?.role_id || '',
    allowed: ace?.allowed ?? true,
    propagate: ace?.propagate ?? true,
    ace_type: ace?.ace_type || 'user'
  });

  useEffect(() => {
    Promise.all([
      api.getEndpoints(token),
      api.getUsers(token),
      api.getGroups(token),
      api.getRoles(token)
    ]).then(([endpoints, users, groups, roles]) => {
      setEndpoints(endpoints);
      setUsers(users);
      setGroups(groups);
      setRoles(roles);
    });
  }, [token]);

  const handleSubmit = async (e) => {
    e.preventDefault();

    const data = {
      ...formData,
      [formData.ace_type === 'user' ? 'user_id' : 'group_id']:
        formData.ace_type === 'user' ? formData.user_id : formData.group_id
    };
    delete data.ace_type;
    delete data.user_id;
    delete data.group_id;

    if (formData.ace_type === 'user') {
      data.user_id = formData.user_id;
    } else {
      data.group_id = formData.group_id;
    }

    try {
      if (ace) {
        await api.updateACE(token, ace.ace_id, data);
      } else {
        await api.createACE(token, data);
      }
      onSave();
    } catch (error) {
      alert(error.message);
    }
  };

  return (
    <form onSubmit={handleSubmit}>
      <DialogContent>
        {/* Path Selection */}
        <TextField
          select
          label="Resource Path"
          value={formData.path}
          onChange={(e) => setFormData({ ...formData, path: e.target.value })}
          fullWidth
          margin="normal"
          required
        >
          {endpoints.map((ep) => (
            <MenuItem key={ep.endpoint} value={ep.endpoint}>
              {ep.name}
            </MenuItem>
          ))}
        </TextField>

        {/* User/Group Selection */}
        <Select
          value={formData.ace_type}
          onChange={(e) => setFormData({ ...formData, ace_type: e.target.value })}
          fullWidth
        >
          <MenuItem value="user">User</MenuItem>
          <MenuItem value="group">User Group</MenuItem>
        </Select>

        {formData.ace_type === 'user' ? (
          <TextField
            select
            label="User"
            value={formData.user_id}
            onChange={(e) => setFormData({ ...formData, user_id: e.target.value })}
            fullWidth
            margin="normal"
            required
          >
            {users.map((user) => (
              <MenuItem key={user.user_id} value={user.user_id}>
                {user.username}
              </MenuItem>
            ))}
          </TextField>
        ) : (
          <TextField
            select
            label="User Group"
            value={formData.group_id}
            onChange={(e) => setFormData({ ...formData, group_id: e.target.value })}
            fullWidth
            margin="normal"
            required
          >
            {groups.map((group) => (
              <MenuItem key={group.user_group_id} value={group.user_group_id}>
                {group.name}
              </MenuItem>
            ))}
          </TextField>
        )}

        {/* Role Selection */}
        <TextField
          select
          label="Role"
          value={formData.role_id}
          onChange={(e) => setFormData({ ...formData, role_id: e.target.value })}
          fullWidth
          margin="normal"
          required
        >
          {roles.map((role) => (
            <MenuItem key={role.role_id} value={role.role_id}>
              {role.name}
            </MenuItem>
          ))}
        </TextField>

        {/* Allow/Deny */}
        <FormControlLabel
          control={
            <Switch
              checked={formData.allowed}
              onChange={(e) => setFormData({ ...formData, allowed: e.target.checked })}
            />
          }
          label={formData.allowed ? 'Allow Access' : 'Deny Access'}
        />

        {/* Propagate */}
        <FormControlLabel
          control={
            <Switch
              checked={formData.propagate}
              onChange={(e) => setFormData({ ...formData, propagate: e.target.checked })}
            />
          }
          label="Propagate to Child Paths"
        />
      </DialogContent>

      <DialogActions>
        <Button onClick={onCancel}>Cancel</Button>
        <Button type="submit" variant="contained">
          {ace ? 'Save' : 'Create'}
        </Button>
      </DialogActions>
    </form>
  );
}

// ACE List Component
export default function ACLManagement({ token }) {
  const [aces, setAces] = useState([]);
  const [loading, setLoading] = useState(false);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingACE, setEditingACE] = useState(null);

  const loadACEs = async () => {
    setLoading(true);
    try {
      const data = await api.getACEs(token);
      setAces(data);
    } catch (error) {
      alert(`Loading failed: ${error.message}`);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadACEs();
  }, [token]);

  const handleCreate = () => {
    setEditingACE(null);
    setDialogOpen(true);
  };

  const handleEdit = (ace) => {
    setEditingACE(ace);
    setDialogOpen(true);
  };

  const handleDelete = async (aceId) => {
    if (!confirm('Are you sure you want to delete this ACE?')) return;

    try {
      await api.deleteACE(token, aceId);
      loadACEs();
    } catch (error) {
      alert(`Deletion failed: ${error.message}`);
    }
  };

  const handleSave = () => {
    setDialogOpen(false);
    loadACEs();
  };

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
        <h2>Access Control List (ACL)</h2>
        <Button
          variant="contained"
          startIcon={<Add />}
          onClick={handleCreate}
        >
          New ACE
        </Button>
      </div>

      {loading ? (
        <p>Loading...</p>
      ) : (
        <Table>
          <thead>
            <tr>
              <th>Path</th>
              <th>User/Group</th>
              <th>Role</th>
              <th>Allowed</th>
              <th>Propagate</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {aces.map((ace) => (
              <tr key={ace.ace_id}>
                <td>{ace.path}</td>
                <td>{ace.ace_type === 'user' ? ace.user_id : ace.group_id}</td>
                <td>{ace.role_id}</td>
                <td>{ace.allowed ? '✓' : '✗'}</td>
                <td>{ace.propagate ? '✓' : '✗'}</td>
                <td>
                  <IconButton onClick={() => handleEdit(ace)}>
                    <Edit />
                  </IconButton>
                  <IconButton onClick={() => handleDelete(ace.ace_id)}>
                    <Delete />
                  </IconButton>
                </td>
              </tr>
            ))}
          </tbody>
        </Table>
      )}

      <Dialog open={dialogOpen} onClose={() => setDialogOpen(false)} maxWidth="md" fullWidth>
        <DialogTitle>{editingACE ? 'Edit ACE' : 'New ACE'}</DialogTitle>
        <ACEForm
          token={token}
          ace={editingACE}
          onSave={handleSave}
          onCancel={() => setDialogOpen(false)}
        />
      </Dialog>
    </div>
  );
}
```

---

## Implementation Checklist

### Basic Features
- [ ] Fetch and display ACE list
- [ ] Create new ACE
- [ ] Edit existing ACE
- [ ] Delete ACE
- [ ] Fetch and display available endpoints

### Form Features
- [ ] Path selector (dropdown/tree)
- [ ] User/group selector
- [ ] Role selector
- [ ] Allow/deny toggle
- [ ] Propagate switch
- [ ] Form validation

### User Experience
- [ ] Loading state display
- [ ] Error notifications
- [ ] Success notifications
- [ ] Delete confirmation dialog
- [ ] List filtering/search

### Advanced Features
- [ ] Batch operations
- [ ] ACE export/import
- [ ] Permission preview
- [ ] Change history

---

## References

### Related Documentation
- [RBAC + ACL Permission System Implementation Guide](../gns3-server/rbac-acl-权限系统实现说明.md)
- [RBAC + ACL Implementation Guide](../gns3-server/rbac-acl-implementation-guide.md)

### API Specifications
- OpenAPI/Swagger: `/static/swagger-ui-bundle.js`
- ReDoc: `/static/redoc.standalone.js`

### Test Data
```javascript
// Example ACEs for testing
const exampleACEs = [
  {
    path: "/projects",
    ace_type: "user",
    user_id: "admin-user-id",
    role_id: "user-role-id",
    allowed: true,
    propagate: true
  },
  {
    path: "/projects/sensitive",
    ace_type: "group",
    group_id: "auditors-group-id",
    role_id: "auditor-role-id",
    allowed: false,
    propagate: false
  }
];
```

---

**Document Version**: 1.0
**Last Updated**: 2026-03-06
