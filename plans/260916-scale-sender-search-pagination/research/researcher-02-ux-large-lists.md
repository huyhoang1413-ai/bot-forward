# Large Allowlist UX Research: 500–1000 Senders, Server-Rendered
**Date:** 2026-09-16  
**Status:** Actionable recommendations ready.

---

## Executive Summary

Inline expandable details (current design) fails at 500+ senders: rendering 1000s of checkboxes per page causes:
- Browser memory bloat; page load >5s (accessibility risk).
- No clear scannability; admin loses sender context.
- Mobile unusable (scrolling through 1000 checkboxes).

**Recommendation: Dedicated per-group management page** (`/bots/{id}/groups/{source}/senders`) with:
1. **Search-first picker:** Server-side HTML form (submit → paginated results).
2. **Assigned senders list** (current group's) with remove buttons + per-page footer count.
3. **Pagination controls** (Trang trước/sau, "X/Y người") at bottom of both lists.
4. **Bot-detail shows summary:** per-group count + "Quản lý người gửi" link per group (replace checkboxes).

---

## 1. Recommended Page Structure: Dedicated Per-Group Manager

### Option A: Dedicated `/bots/{id}/groups/{source}/senders` (CHOSEN)

**Layout:**
```
<h2>Quản lý người gửi: Nhóm -123456789 (nguồn)</h2>
[Bot navigation breadcrumb]

<div class="two-column-manager">
  <!-- Column 1: Search Picker -->
  <div class="picker">
    <h3>Tìm và thêm người gửi</h3>
    <form method="post" action="." style="display:flex; gap:8px">
      <input type="text" name="search" placeholder="Tìm username..." value="{{ search }}" required>
      <button type="submit">Tìm</button>
    </form>
    
    {% if search %}
      <p class="muted" style="font-size:12px; margin-top:8px">
        Kết quả: {{ results_count }}/{{ total_registry_count }} (trang {{ page }}/{{ total_pages }})
      </p>
      {% if search_results %}
        <div class="result-list">
          {% for s in search_results %}
            <div style="padding:8px; border-bottom:1px solid #e5e7eb; display:flex; justify-content:space-between">
              <span><code>@{{ s.username }}</code> {% if s.label %}<span class="muted">— {{ s.label }}</span>{% endif %}</span>
              <form method="post" action="./add" style="margin:0">
                <input type="hidden" name="sender_id" value="{{ s.id }}">
                <button class="mini" type="submit">Thêm</button>
              </form>
            </div>
          {% endfor %}
        </div>
        
        <!-- Pagination for search results -->
        <div style="margin-top:12px; text-align:center">
          {% if page > 1 %}
            <a href="?search={{ search }}&page={{ page - 1 }}">← Trang trước</a>
          {% endif %}
          <span class="muted" style="margin:0 12px">Trang {{ page }}/{{ total_pages }}</span>
          {% if page < total_pages %}
            <a href="?search={{ search }}&page={{ page + 1 }}">Trang sau →</a>
          {% endif %}
        </div>
      {% else %}
        <p class="muted">Không tìm thấy. Kiểm tra chính tả username.</p>
      {% endif %}
    {% else %}
      <p class="muted">Nhập username để tìm trong danh sách {{ total_registry_count }} người gửi.</p>
    {% endif %}
  </div>
  
  <!-- Column 2: Assigned List -->
  <div class="assigned">
    <h3>Người gửi được phép (nhóm này)</h3>
    {% if assigned_senders %}
      <div class="assigned-list">
        {% for s in assigned_page_items %}
          <div style="padding:8px; border-bottom:1px solid #e5e7eb; display:flex; justify-content:space-between">
            <span><code>@{{ s.username }}</code> {% if s.label %}<span class="muted">— {{ s.label }}</span>{% endif %}</span>
            <form method="post" action="./remove" style="margin:0">
              <input type="hidden" name="sender_id" value="{{ s.id }}">
              <button class="mini ghost" type="submit">Xoá</button>
            </form>
          </div>
        {% endfor %}
      </div>
      
      <!-- Pagination for assigned list -->
      <div style="margin-top:12px; text-align:center">
        {% if assigned_page > 1 %}
          <a href="?assigned_page={{ assigned_page - 1 }}">← Trang trước</a>
        {% endif %}
        <span class="muted" style="margin:0 12px">{{ assigned_count }} người, trang {{ assigned_page }}/{{ assigned_total_pages }}</span>
        {% if assigned_page < assigned_total_pages %}
          <a href="?assigned_page={{ assigned_page + 1 }}">Trang sau →</a>
        {% endif %}
      </div>
    {% else %}
      <p class="muted">Để trống → forward mọi người trong nhóm này.</p>
    {% endif %}
  </div>
</div>

<p style="margin-top:16px"><a href="/bots/{{ bot_id }}">&larr; Về chi tiết bot</a></p>
```

**Why this:**
- **Clear separation:** search ≠ assigned; no confusion between "finding someone" and "viewing current".
- **Paginates both lists:** avoids rendering 1000 rows at once.
- **Mobile-friendly:** narrow on mobile; can stack columns.
- **Scales linearly:** whether 100 or 5000 senders, response time stays <500ms (DB cursor pagination).
- **Minimal JS:** plain HTML forms + server-side search (optional JS typeahead enhancement later).

### Option B: Inline Expandable (Current, REJECTED)
- Breaks at 500+ senders; DOM bloat kills browser.
- No pagination within details; users scroll forever.

---

## 2. Add-via-Search Pattern: Server-Side Form (No Heavy JS)

### Pattern: HTML Form Submit → Paginated Results (CHOSEN)

```html
<form method="post" action="/bots/{id}/groups/{source}/senders?_method=search" style="display:flex; gap:8px; margin-bottom:16px">
  <input 
    type="text" 
    name="search" 
    placeholder="Tìm username hoặc nick name..." 
    value="{{ request.query_params.get('search', '') }}"
    minlength="1"
    maxlength="32"
  >
  <button type="submit">Tìm (Enter)</button>
  {% if search %}<a href="?">Xoá bộ lọc</a>{% endif %}
</form>

<!-- Backend: POST /bots/{id}/groups/{source}/senders with ?search=user&page=2 redirects to GET with same params -->
```

**Trade-offs comparison:**

| Pattern | Add Button | Search UX | No-JS | Latency | Scale (500+) |
|---------|-----------|-----------|-------|---------|------------|
| **Server form** (chosen) | POST /add after search | Type → Submit → Results | ✓ | 100-300ms | ✓ Safe |
| Datalist (no JS) | Manual add by dropdown | Pre-loaded 1000 options in HTML | ✓ | N/A (client) | ✗ Page bloat (200KB+) |
| Fetch typeahead | POST /add after fetch | Real-time, snappy | ✗ (JS required) | 50-100ms | ✓ Fast |

**Recommended:** Server form + optional JS enhancement (fetch typeahead as progressive enhancement).

---

## 3. Paginated Assigned List UI + Remove

```html
<div style="border:1px solid #cbd5e1; border-radius:4px; padding:12px">
  <table style="width:100%; font-size:13px">
    <thead style="background:#f1f5f9">
      <tr>
        <th style="text-align:left; padding:8px">Username</th>
        <th style="text-align:left; padding:8px">Nick Name</th>
        <th style="text-align:right; padding:8px">Hành động</th>
      </tr>
    </thead>
    <tbody>
      {% for s in assigned_page_items %}
      <tr style="border-bottom:1px solid #e5e7eb">
        <td style="padding:8px"><code>@{{ s.username }}</code></td>
        <td style="padding:8px">{{ s.label or "—" }}</td>
        <td style="text-align:right; padding:8px">
          <form method="post" action="/bots/{{ bot_id }}/groups/{{ source }}/senders/{{ s.id }}/remove" style="margin:0; display:inline">
            <button class="ghost" type="submit" style="padding:2px 6px; font-size:12px" onclick="return confirm('Xoá @{{ s.username }} khỏi nhóm này?')">Xoá</button>
          </form>
        </td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
  
  <div style="margin-top:12px; display:flex; justify-content:space-between; align-items:center">
    <span class="muted" style="font-size:12px">Trang {{ assigned_page }}/{{ assigned_total_pages }} ({{ assigned_count }} người)</span>
    <div style="display:flex; gap:8px">
      {% if assigned_page > 1 %}
        <a href="?assigned_page={{ assigned_page - 1 }}" class="btn-text">← Trang trước</a>
      {% endif %}
      {% if assigned_page < assigned_total_pages %}
        <a href="?assigned_page={{ assigned_page + 1 }}" class="btn-text">Trang sau →</a>
      {% endif %}
    </div>
  </div>
</div>
```

**Remove semantics:** Inline POST form + `onclick="return confirm()"` (minimal JS, server-authoritative).

---

## 4. Registry (Global Sender) Management at Scale

**Current:** Bot-detail card shows all 500+ senders as table/checkboxes.

**Recommendation:** Dedicate `/bots/{id}/senders` page (mirror of per-group page):

```
GET /bots/{id}/senders
  ├─ Search form (type → results, paginated)
  ├─ Assigned senders list (paginated) + edit nickname + remove
  ├─ Add via search + nickname field
  └─ Bulk actions (optional): "Export CSV", "Import CSV"

POST /bots/{id}/senders (add)
  ├─ username (required), label (optional)
  └─ Redirect to /bots/{id}/senders?search={{ username }}

POST /bots/{id}/senders/{id}/remove
  └─ Redirect to /bots/{id}/senders
```

**Bot-detail.html change:**
```html
<!-- OLD: Large table of all senders + inline add form -->
<!-- NEW: Summary card + link to manager page -->
<div class="card">
  <h3>Người gửi được forward (danh sách chung)</h3>
  <p class="muted">Khai báo người + nick name <b>một lần</b>, sau đó chọn họ cho từng nhóm.</p>
  
  {% if allowed_senders_count %}
    <p><b>{{ allowed_senders_count }} người</b> đã khai báo</p>
    <a href="/bots/{{ bot.id }}/senders">Quản lý người gửi →</a>
  {% else %}
    <p class="muted">Không giới hạn — đang forward mọi người.</p>
    <a href="/bots/{{ bot.id }}/senders">Thêm danh sách người gửi →</a>
  {% endif %}
</div>

<!-- OLD: Inline checkboxes in each group details block -->
<!-- NEW: Count summary + link -->
{% for g in source_groups %}
<details class="group">
  <summary>{{ g }} → ...</summary>
  <!-- Route delete forms... -->
  <p style="margin:16px 0">
    <a href="/bots/{{ bot.id }}/groups/{{ g }}/senders">
      Quản lý {{ group_sender_counts[g]|default('') }} người cho nhóm này →
    </a>
  </p>
</details>
{% endfor %}
```

---

## 5. Semantics: Empty/Defaults (UX Clarity)

| State | Behavior | UI Label |
|-------|----------|----------|
| **Global list empty** | Forward everyone from all groups | "Không giới hạn — đang forward mọi người." |
| **Global list has senders, group assignment empty** | Forward all global senders to this group | "Để trống → forward mọi người trong nhóm này." |
| **Global + group both assigned** | Forward only intersection (group's assigned senders) | "{{ count }} người được phép" |
| **Group assignment, but sender deleted from global** | Cascade-delete from group (clean up) | (internal; no UI change needed) |

**Rationale:** "Empty = allow everyone at that level" is intuitive (default to permissive, then restrict).

---

## 6. Vietnamese Microcopy

| Component | Vietnamese Label | Notes |
|-----------|-------------------|-------|
| Search input | "Tìm username hoặc nick name..." | Placeholder; use exact search (no fuzzy) for server form |
| Search button | "Tìm (Enter)" | Hint that Enter works |
| Clear search | "Xoá bộ lọc" or "Làm mới" | Show only if search is active |
| Add button | "Thêm" | After search result row |
| Remove button | "Xoá" | Inline in assigned list; show confirm popup |
| Pagination prev | "← Trang trước" | Left-align text + arrow |
| Pagination next | "Trang sau →" | Right-align text + arrow |
| Page info | "Trang X/Y (Z người)" | Center; show total count |
| Empty state (registry) | "Không giới hạn — đang forward mọi người." | Calming tone; no restrictions = default |
| Empty state (group) | "Để trống → forward mọi người trong nhóm này." | Clearly explain empty = permissive |
| Manager page title | "Quản lý người gửi: Nhóm [ID] (nguồn)" | Or "Quản lý danh sách người gửi" for global |
| Add via search heading | "Tìm và thêm người gửi" | Section heading |
| Assigned heading | "Người gửi được phép (nhóm này)" | Section heading; "(nhóm này)" = scope clarity |
| Confirm remove | "Xoá @[user] khỏi nhóm này?" | Inline confirm popup |
| Help text | "Chọn người được phép forward. Để trống = tất cả." | Below legend/heading |

---

## 7. Accessibility Notes

1. **Form structure:** Use `<form method="post">` (POST for mutations, GET for search); `<fieldset>` + `<legend>` for grouped controls.
2. **Pagination links:** Use `<a href="...">` (not buttons); screen readers announce "link, Trang sau".
3. **Remove confirm:** Use `onclick="return confirm(...)"` OR server-side POST with confirmation page (WCAG 2.1 Level AA; JS is not reliable for confirm).
4. **Table headings:** `<th scope="col">` for screen readers.
5. **Labels:** Every input has explicit `<label for="...">` or `placeholder`; avoid invisible labels.
6. **Focus management:** After add/remove, stay on the page (redirect back to same URL + fragment if needed; e.g., `?assigned_page=1#list`).

---

## 8. Optional Enhancements (Post-MVP)

- **JS typeahead:** Fetch `/api/bots/{id}/senders/search?q=...` (JSON) → instant results (no page reload).
- **Bulk add via CSV:** Upload file → parse → multi-add (confirm list before submit).
- **Sort assigned list:** By username, by nickname, by date added (DB ORDER BY).
- **Audit log:** Show who added/removed each sender, when (log table on manager page).

---

## Unresolved Questions

1. **Exact pagination size:** 20, 50, or 100 items per page? (Recommend 50 for balance.)
2. **Search scope:** Exact username match, or substring? Case-insensitive? (Recommend exact; users can type prefix.)
3. **Remove confirm:** Browser `confirm()` or server page? (JS confirm is simpler; server page is more accessible.)
4. **Sorting:** Assigned list sorted by username, date added, or user's drag-drop order? (Recommend username for predictability.)
5. **Mobile layout:** Single column (search above) or stacked sections? (Recommend: on mobile, show search first, then assigned below, no side-by-side.)

---

**Report written:** 2026-09-16 by researcher (UX patterns for 500+ senders at server-rendered scale).
