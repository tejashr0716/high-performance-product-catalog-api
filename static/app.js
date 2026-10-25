// CatalogEngine Client Application
let state = {
    page: 1,
    pageSize: 20,
    totalPages: 1,
    adminKey: sessionStorage.getItem("adminKey") || null,
    editingProductId: null,
};

let debounceTimer = null;

document.addEventListener("DOMContentLoaded", async () => {
    await loadCategories();
    await loadBrands();
    setupEventListeners();
    updateAdminUI();
    await fetchProducts();
});

// ==============================================================================
// Data Fetching & Rendering
// ==============================================================================

async function fetchProducts() {
    const q = document.getElementById("search-input").value.trim();
    const cat = document.getElementById("category-select").value;
    const brand = document.getElementById("brand-select").value;
    const minP = document.getElementById("min-price").value;
    const maxP = document.getElementById("max-price").value;
    const inStock = document.getElementById("instock-check").checked;
    const [sortBy, sortDir] = document.getElementById("sort-select").value.split("_");

    const params = new URLSearchParams({
        page: state.page,
        page_size: state.pageSize,
        sort_by: sortBy,
        sort_dir: sortDir,
    });

    if (q) params.set("q", q);
    if (cat) params.set("category_id", cat);
    if (brand) params.set("brand_id", brand);
    if (minP) params.set("min_price", minP);
    if (maxP) params.set("max_price", maxP);
    if (inStock) params.set("in_stock", "true");

    const grid = document.getElementById("product-grid");
    grid.innerHTML = '<div style="grid-column: 1/-1; text-align: center; color: var(--text-muted); padding: 3rem;">Loading catalog...</div>';

    const t0 = performance.now();
    try {
        const res = await fetch(`/api/v1/products?${params.toString()}`);
        const t1 = performance.now();
        const duration = Math.round(t1 - t0);

        const cacheStatus = res.headers.get("X-Cache-Status") || "MISS";
        const processTime = res.headers.get("X-Process-Time-Ms") || duration;

        // Update Nav Pills
        const cachePill = document.getElementById("cache-stat");
        cachePill.textContent = cacheStatus;
        cachePill.className = cacheStatus.includes("HIT") ? "hit" : "miss";

        document.getElementById("latency-stat").textContent = `${processTime} ms`;

        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();

        renderProducts(data.items);
        updatePagination(data.pagination);
    } catch (err) {
        grid.innerHTML = `<div style="grid-column: 1/-1; text-align: center; color: var(--danger); padding: 3rem;">Error loading products: ${err.message}</div>`;
    }
}

function renderProducts(items) {
    const grid = document.getElementById("product-grid");
    if (!items || items.length === 0) {
        grid.innerHTML = '<div style="grid-column: 1/-1; text-align: center; color: var(--text-muted); padding: 3rem;">No products match your criteria.</div>';
        return;
    }

    grid.innerHTML = items.map(p => `
        <div class="product-card" data-id="${p.id}">
            <div>
                <div class="card-top">
                    <span>${p.sku}</span>
                    <span>★ ${parseFloat(p.rating).toFixed(1)}</span>
                </div>
                <h4 class="card-title">${escapeHtml(p.title)}</h4>
                <div class="card-meta">${escapeHtml(p.brand_name || '')} · ${escapeHtml(p.category_name || '')}</div>
                <p class="card-desc">${escapeHtml(p.description || 'No description provided.')}</p>
            </div>
            <div>
                <div class="card-footer">
                    <span class="price">₹${parseFloat(p.price).toLocaleString('en-IN', { minimumFractionDigits: 2 })}</span>
                    <span class="badge ${p.stock_quantity > 0 ? 'badge-instock' : 'badge-outofstock'}">
                        ${p.stock_quantity > 0 ? `${p.stock_quantity} in stock` : 'Out of stock'}
                    </span>
                </div>
                ${state.adminKey ? `
                    <div class="admin-actions">
                        <button class="btn btn-secondary btn-sm" onclick="openEditModal(${p.id})">Edit</button>
                        <button class="btn btn-danger btn-sm" onclick="archiveProduct(${p.id})">Archive</button>
                    </div>
                ` : ''}
            </div>
        </div>
    `).join('');
}

function updatePagination(meta) {
    state.page = meta.page;
    state.totalPages = meta.total_pages || 1;

    document.getElementById("count-start").textContent = meta.total_items > 0 ? ((meta.page - 1) * meta.page_size + 1) : 0;
    document.getElementById("count-end").textContent = Math.min(meta.page * meta.page_size, meta.total_items);
    document.getElementById("count-total").textContent = meta.total_items;

    document.getElementById("cur-page").textContent = meta.page;
    document.getElementById("max-page").textContent = state.totalPages;

    document.getElementById("btn-prev-page").disabled = !meta.has_prev;
    document.getElementById("btn-next-page").disabled = !meta.has_next;
}

// ==============================================================================
// Metadata Loaders
// ==============================================================================

async function loadCategories() {
    try {
        const res = await fetch("/api/v1/categories");
        if (res.ok) {
            const cats = await res.json();
            const select = document.getElementById("category-select");
            const formSelect = document.getElementById("form-category");

            cats.forEach(c => {
                const prefix = c.parent_id ? "— " : "";
                const opt = new Option(`${prefix}${c.name}`, c.id);
                select.add(opt.cloneNode(true));
                if (c.parent_id) { // Only leaf subcategories for product assignment
                    formSelect.add(new Option(c.name, c.id));
                }
            });
        }
    } catch (e) {
        console.error("Failed to load categories:", e);
    }
}

async function loadBrands() {
    try {
        const res = await fetch("/api/v1/brands");
        if (res.ok) {
            const brands = await res.json();
            const select = document.getElementById("brand-select");
            const formSelect = document.getElementById("form-brand");

            brands.forEach(b => {
                select.add(new Option(b.name, b.id));
                formSelect.add(new Option(b.name, b.id));
            });
        }
    } catch (e) {
        console.error("Failed to load brands:", e);
    }
}

// ==============================================================================
// Events & Search Debouncing
// ==============================================================================

function setupEventListeners() {
    // 300ms Debounce Search
    document.getElementById("search-input").addEventListener("input", () => {
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(() => {
            state.page = 1;
            fetchProducts();
        }, 300);
    });

    // Filter Change Listeners
    ["category-select", "brand-select", "sort-select"].forEach(id => {
        document.getElementById(id).addEventListener("change", () => {
            state.page = 1;
            fetchProducts();
        });
    });

    ["min-price", "max-price"].forEach(id => {
        document.getElementById(id).addEventListener("change", () => {
            state.page = 1;
            fetchProducts();
        });
    });

    document.getElementById("instock-check").addEventListener("change", () => {
        state.page = 1;
        fetchProducts();
    });

    // Reset Filters
    document.getElementById("btn-reset-filters").addEventListener("click", () => {
        document.getElementById("search-input").value = "";
        document.getElementById("category-select").value = "";
        document.getElementById("brand-select").value = "";
        document.getElementById("min-price").value = "";
        document.getElementById("max-price").value = "";
        document.getElementById("instock-check").checked = false;
        document.getElementById("sort-select").value = "id_desc";
        state.page = 1;
        fetchProducts();
    });

    // Pagination Click
    document.getElementById("btn-prev-page").addEventListener("click", () => {
        if (state.page > 1) {
            state.page--;
            fetchProducts();
        }
    });

    document.getElementById("btn-next-page").addEventListener("click", () => {
        if (state.page < state.totalPages) {
            state.page++;
            fetchProducts();
        }
    });

    // Admin Modal Controls
    document.getElementById("btn-admin-toggle").addEventListener("click", () => {
        document.getElementById("admin-modal").classList.add("open");
    });
    document.getElementById("admin-modal-close").addEventListener("click", () => {
        document.getElementById("admin-modal").classList.remove("open");
    });
    document.getElementById("btn-cancel-admin").addEventListener("click", () => {
        document.getElementById("admin-modal").classList.remove("open");
    });
    document.getElementById("btn-save-admin-key").addEventListener("click", () => {
        const val = document.getElementById("admin-key-input").value.trim();
        if (val) {
            state.adminKey = val;
            sessionStorage.setItem("adminKey", val);
            document.getElementById("admin-modal").classList.remove("open");
            updateAdminUI();
            fetchProducts();
        }
    });

    // Create Modal
    document.getElementById("btn-create-modal").addEventListener("click", () => {
        openCreateModal();
    });
    document.getElementById("product-modal-close").addEventListener("click", () => {
        document.getElementById("product-modal").classList.remove("open");
    });
    document.getElementById("btn-cancel-product").addEventListener("click", () => {
        document.getElementById("product-modal").classList.remove("open");
    });

    // Save Product
    document.getElementById("product-form").addEventListener("submit", async (e) => {
        e.preventDefault();
        await handleSaveProduct();
    });
}

function updateAdminUI() {
    const btnToggle = document.getElementById("btn-admin-toggle");
    const btnCreate = document.getElementById("btn-create-modal");

    if (state.adminKey) {
        btnToggle.textContent = "🔒 Admin Active";
        btnToggle.classList.remove("btn-outline");
        btnToggle.classList.add("btn-primary");
        btnCreate.style.display = "block";
    } else {
        btnToggle.textContent = "🔑 Admin Mode";
        btnToggle.classList.remove("btn-primary");
        btnToggle.classList.add("btn-outline");
        btnCreate.style.display = "none";
    }
}

// ==============================================================================
// Admin Operations
// ==============================================================================

function openCreateModal() {
    state.editingProductId = null;
    document.getElementById("product-modal-title").textContent = "Create New Product";
    document.getElementById("product-form").reset();
    document.getElementById("form-sku").disabled = false;
    document.getElementById("form-slug").disabled = false;
    document.getElementById("product-modal").classList.add("open");
}

async function openEditModal(productId) {
    try {
        const res = await fetch(`/api/v1/products/${productId}`);
        if (!res.ok) throw new Error("Failed to load product");
        const p = await res.json();

        state.editingProductId = productId;
        document.getElementById("product-modal-title").textContent = `Edit Product #${productId}`;
        document.getElementById("form-sku").value = p.sku;
        document.getElementById("form-sku").disabled = true; // Immutable SKU
        document.getElementById("form-slug").value = p.slug;
        document.getElementById("form-slug").disabled = true;
        document.getElementById("form-title").value = p.title;
        document.getElementById("form-price").value = p.price;
        document.getElementById("form-stock").value = p.stock_quantity;
        document.getElementById("form-rating").value = p.rating;
        document.getElementById("form-category").value = p.category_id;
        document.getElementById("form-brand").value = p.brand_id;
        document.getElementById("form-desc").value = p.description || "";

        document.getElementById("product-modal").classList.add("open");
    } catch (e) {
        alert(e.message);
    }
}

async function handleSaveProduct() {
    const isEdit = state.editingProductId !== null;
    const body = {
        title: document.getElementById("form-title").value.trim(),
        price: parseFloat(document.getElementById("form-price").value),
        stock_quantity: parseInt(document.getElementById("form-stock").value, 10),
        rating: parseFloat(document.getElementById("form-rating").value),
        category_id: parseInt(document.getElementById("form-category").value, 10),
        brand_id: parseInt(document.getElementById("form-brand").value, 10),
        description: document.getElementById("form-desc").value.trim(),
    };

    if (!isEdit) {
        body.sku = document.getElementById("form-sku").value.trim();
        body.slug = document.getElementById("form-slug").value.trim();
    }

    const url = isEdit ? `/api/v1/products/${state.editingProductId}` : `/api/v1/products`;
    const method = isEdit ? "PATCH" : "POST";

    try {
        const res = await fetch(url, {
            method,
            headers: {
                "Content-Type": "application/json",
                "X-Admin-Key": state.adminKey,
            },
            body: JSON.stringify(body),
        });

        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.detail || `Error ${res.status}`);
        }

        document.getElementById("product-modal").classList.remove("open");
        alert(isEdit ? "Product updated and cache invalidated!" : "Product created and list cache purged!");
        await fetchProducts();
    } catch (err) {
        alert(`Operation failed: ${err.message}`);
    }
}

async function archiveProduct(productId) {
    if (!confirm(`Are you sure you want to soft-archive product #${productId}? It will immediately be purged from Redis.`)) {
        return;
    }

    try {
        const res = await fetch(`/api/v1/products/${productId}`, {
            method: "DELETE",
            headers: {
                "X-Admin-Key": state.adminKey,
            },
        });

        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.detail || `Error ${res.status}`);
        }

        alert(`Product #${productId} archived and Redis cache invalidated.`);
        await fetchProducts();
    } catch (err) {
        alert(`Failed to delete: ${err.message}`);
    }
}

function escapeHtml(str) {
    if (!str) return '';
    return str.replace(/[&<>'"]/g, tag => ({
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        "'": '&#39;',
        '"': '&quot;'
    }[tag] || tag));
}
