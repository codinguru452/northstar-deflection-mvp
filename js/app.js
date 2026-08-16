const API_BASE = "/api";

function getToken() { return localStorage.getItem("northstar_token"); }
function setToken(token) { token ? localStorage.setItem("northstar_token", token) : localStorage.removeItem("northstar_token"); }

async function api(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (options.body && !headers["Content-Type"]) headers["Content-Type"] = "application/json";
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  const response = await fetch(`${API_BASE}${path}`, { ...options, headers });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    if (response.status === 401) { setToken(null); updateAccountLink(); }
    throw new Error(data.error || "Something went wrong.");
  }
  return data;
}

function showToast(message) {
  let toast = document.getElementById("northstarToast");
  if (!toast) {
    toast = document.createElement("div");
    toast.id = "northstarToast";
    toast.className = "northstar-toast";
    document.body.appendChild(toast);
  }
  toast.textContent = message;
  toast.classList.add("show");
  clearTimeout(window.northstarToastTimer);
  window.northstarToastTimer = setTimeout(() => toast.classList.remove("show"), 2200);
}

function money(value) {
  return `KSh ${Number(value || 0).toLocaleString("en-KE", { maximumFractionDigits: 0 })}`;
}
function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, c => ({ "&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#039;" }[c]));
}

function updateAccountLink() {
  document.querySelectorAll('a[aria-label*="Account"], a[aria-label*="account"], a[href="login.html"]').forEach(link => {
    if (link.getAttribute("aria-label") === "Shopping Cart") return;
    if (getToken()) { link.href = "account.html"; link.setAttribute("aria-label", "My Account"); }
    else link.href = "login.html";
  });
}

async function updateCartCount() {
  const links = document.querySelectorAll('a[href="cart.html"]');
  if (!links.length || !getToken()) return;
  try {
    const data = await api("/cart");
    const count = data.items.reduce((sum, item) => sum + Number(item.quantity), 0);
    links.forEach(link => {
      let badge = link.querySelector(".cart-count");
      if (!badge) { badge = document.createElement("span"); badge.className = "cart-count"; link.style.position = "relative"; link.appendChild(badge); }
      badge.textContent = count; badge.style.display = count ? "inline-flex" : "none";
    });
  } catch (_) {}
}

function setupShop() {
  const products = document.querySelectorAll(".product-item");
  if (!products.length) return;
  products.forEach((card, index) => {
    const addButton = card.querySelector(".icon-cross");
    if (!addButton) return;
    addButton.setAttribute("role", "button"); addButton.setAttribute("tabindex", "0");
    addButton.setAttribute("data-tooltip", "Add to cart");
    addButton.setAttribute("aria-label", "Add to cart");
    const add = async event => {
      event.preventDefault(); event.stopPropagation();
      if (!getToken()) { window.location.href = `login.html?next=${encodeURIComponent("shop.html")}`; return; }
      const productId = Number(card.dataset.productId || index + 1);
      try {
        await api("/cart", { method:"POST", body:JSON.stringify({ product_id:productId, quantity:1 }) });
        addButton.classList.add("added");
        const img = addButton.querySelector("img");
        const oldAlt = img?.alt;
        if (img) img.alt = "Added to cart";
        setTimeout(() => { addButton.classList.remove("added"); if (img && oldAlt) img.alt = oldAlt; }, 700);
        await updateCartCount();
        showToast(`${card.querySelector(".product-title")?.textContent?.trim() || "Item"} added to cart.`);
      } catch (error) { alert(error.message); }
    };
    addButton.addEventListener("click", add);
    addButton.addEventListener("keydown", event => { if (event.key === "Enter" || event.key === " ") add(event); });
  });
}

function customerToolsNav(active = "cart") {
  const items = [
    ["cart", "Shopping Cart", "cart.html"],
    ["orders", "My Orders", "account.html#orders"],
    ["track", "Track Order", "track-order.html"],
    ["returns", "Returns / Refunds", "return-refund.html"]
  ];
  return `<div class="northstar-tools-nav mb-5">${items.map(([key,label,url]) => `<a class="${active===key?"active":""}" href="${url}">${label}</a>`).join("")}</div>`;
}

async function renderCart() {
  const container = document.getElementById("dynamicCart");
  if (!container) return;
  if (!getToken()) {
    container.innerHTML = `<div class="text-center py-5"><h3 class="h4 mb-3">Please sign in to view your cart.</h3><a href="login.html" class="btn btn-black">Sign In</a></div>`;
    return;
  }
  try {
    const data = await api("/cart");
    if (!data.items.length) {
      container.innerHTML = `<div class="text-center py-5"><h3 class="h4 mb-3">Your cart is empty.</h3><p class="text-muted mb-4">Add something you love from the shop.</p><a href="shop.html" class="btn btn-black">Continue Shopping</a></div>`;
      await updateCartCount(); return;
    }
    const subtotal = data.items.reduce((sum, item) => sum + Number(item.line_total), 0);
    const rows = data.items.map(item => `<tr>
      <td class="product-thumbnail"><img src="${escapeHtml(item.image)}" alt="${escapeHtml(item.name)}" class="img-fluid" /></td>
      <td class="product-name"><h2 class="h5 text-black">${escapeHtml(item.name)}</h2></td>
      <td>${money(item.price)}</td>
      <td><div class="input-group mb-3 d-flex align-items-center quantity-container" style="max-width:120px">
        <button class="btn btn-outline-black decrease" data-product="${item.product_id}" type="button">&minus;</button>
        <input type="text" class="form-control text-center quantity-amount" value="${item.quantity}" readonly />
        <button class="btn btn-outline-black increase" data-product="${item.product_id}" type="button">&plus;</button>
      </div></td>
      <td>${money(item.line_total)}</td>
      <td><button class="btn btn-black btn-sm remove-cart" data-product="${item.product_id}" type="button">X</button></td>
    </tr>`).join("");
    container.innerHTML = `<div class="table-responsive"><table class="table"><thead><tr><th>Image</th><th>Product</th><th>Price</th><th>Quantity</th><th>Total</th><th></th></tr></thead><tbody>${rows}</tbody></table></div>
      <div class="row justify-content-end"><div class="col-md-5"><div class="border p-4"><h3 class="h5 text-black text-uppercase mb-4">Cart Summary</h3>
      <div class="d-flex justify-content-between mb-3"><span>Subtotal</span><strong>${money(subtotal)}</strong></div>
      <div class="d-flex justify-content-between mb-3"><span>Delivery</span><strong>Calculated at checkout</strong></div>
      <div class="d-flex justify-content-between mb-4"><strong>Total</strong><strong>${money(subtotal)}</strong></div>
      <a href="shop.html" class="btn btn-outline-black me-2">Continue Shopping</a><a href="checkout.html" class="btn btn-black">Checkout</a></div></div></div>`;
    container.querySelectorAll(".increase,.decrease").forEach(button => button.addEventListener("click", async () => {
      const id = Number(button.dataset.product), row = button.closest("tr"), input = row.querySelector(".quantity-amount");
      let quantity = Number(input.value) + (button.classList.contains("increase") ? 1 : -1);
      if (quantity < 0) quantity = 0;
      try { await api("/cart", { method:"PUT", body:JSON.stringify({product_id:id, quantity}) }); await renderCart(); }
      catch (error) { alert(error.message); }
    }));
    container.querySelectorAll(".remove-cart").forEach(button => button.addEventListener("click", async () => {
      try { await api("/cart", { method:"DELETE", body:JSON.stringify({product_id:Number(button.dataset.product)}) }); await renderCart(); }
      catch (error) { alert(error.message); }
    }));
    await updateCartCount();
  } catch (error) { container.innerHTML = `<div class="alert alert-danger">${escapeHtml(error.message)}</div>`; }
}

async function setupLogin() {
  const form = document.getElementById("loginForm"); if (!form) return;
  form.addEventListener("submit", async event => {
    event.preventDefault(); const button = form.querySelector("button[type=submit]"); button.disabled = true;
    try {
      const data = await api("/login", { method:"POST", body:JSON.stringify({ email:form.email.value, password:form.password.value }) });
      setToken(data.token); window.location.href = "shop.html";
    } catch (error) { alert(error.message); } finally { button.disabled = false; }
  });
}

async function setupRegister() {
  const form = document.getElementById("registerForm"); if (!form) return;
  form.addEventListener("submit", async event => {
    event.preventDefault();
    if (form.password.value !== form.confirm_password.value) { alert("Passwords do not match."); return; }
    if (!form.terms.checked) { alert("Please accept the Terms & Conditions and Privacy Policy."); return; }
    const button = form.querySelector("button[type=submit]"); button.disabled = true;
    try {
      const data = await api("/register", { method:"POST", body:JSON.stringify({ full_name:form.full_name.value, email:form.email.value, phone:form.phone.value, password:form.password.value }) });
      setToken(data.token); window.location.href = "shop.html";
    } catch (error) { alert(error.message); } finally { button.disabled = false; }
  });
}

async function setupCheckout() {
  const form = document.getElementById("checkoutForm"), summary = document.getElementById("checkoutSummary");
  if (!form || !summary) return;
  if (!getToken()) { summary.innerHTML = `<div class="alert alert-info">Please <a href="login.html">sign in</a> before checkout.</div>`; form.style.display="none"; return; }
  try {
    const data = await api("/cart");
    if (!data.items.length) { summary.innerHTML=`<div class="alert alert-info">Your cart is empty. <a href="shop.html">Continue shopping</a>.</div>`; form.style.display="none"; return; }
    const subtotal = data.items.reduce((sum,i)=>sum+Number(i.line_total),0);
    summary.innerHTML=`<h3 class="h5 text-black text-uppercase mb-4">Order Summary</h3>${data.items.map(i=>`<div class="d-flex justify-content-between mb-2"><span>${escapeHtml(i.name)} × ${i.quantity}</span><strong>${money(i.line_total)}</strong></div>`).join("")}<hr><div class="d-flex justify-content-between"><strong>Total</strong><strong>${money(subtotal)}</strong></div>`;
  } catch (error) { summary.innerHTML=`<div class="alert alert-danger">${escapeHtml(error.message)}</div>`; return; }
  try { const me=await api("/me"); if(me.customer.address) form.delivery_address.value=me.customer.address; form.full_name.value=me.customer.full_name; form.email.value=me.customer.email; form.phone.value=me.customer.phone; } catch (_) {}
  form.addEventListener("submit", async event => {
    event.preventDefault(); const button=form.querySelector("button[type=submit]"); button.disabled=true;
    try { const data=await api("/orders",{method:"POST",body:JSON.stringify({delivery_address:form.delivery_address.value})}); window.location.href=`account.html?placed=${encodeURIComponent(data.order_number)}#orders`; }
    catch(error){alert(error.message);} finally{button.disabled=false;}
  });
}

async function setupAccount() {
  const root=document.getElementById("accountRoot"); if(!root)return;
  if(!getToken()){window.location.href="login.html";return;}
  try{
    const me=await api("/me");
    root.querySelector("#customerName").textContent=me.customer.full_name;
    root.querySelector("#customerEmail").textContent=me.customer.email;
    root.querySelector("#customerPhone").textContent=me.customer.phone;
    root.querySelector("#customerAddress").textContent=me.customer.address||"No delivery address saved yet.";
    const orders=await api("/orders"), orderBox=root.querySelector("#ordersList");
    orderBox.innerHTML=orders.orders.length?orders.orders.map(o=>`<div class="border rounded p-3 mb-3"><div class="d-flex justify-content-between flex-wrap"><strong>${escapeHtml(o.order_number)}</strong><span class="badge bg-secondary">${escapeHtml(o.status)}</span></div><p class="mb-1 mt-2">${new Date(o.created_at).toLocaleString()}</p><p class="mb-2"><strong>${money(o.total_amount)}</strong></p><a href="track-order.html?order=${encodeURIComponent(o.order_number)}" class="btn btn-sm btn-outline-black">Track Order</a><a href="return-refund.html?order=${encodeURIComponent(o.order_number)}" class="btn btn-sm btn-black ms-2">Return / Refund</a></div>`).join(""):"<p class=\"text-muted\">You have no orders yet.</p>";
    const placed=new URLSearchParams(window.location.search).get("placed");
    if(placed) orderBox.insertAdjacentHTML("beforebegin",`<div class="alert alert-success">Order <strong>${escapeHtml(placed)}</strong> was placed successfully. You can track it using the Track Order page.</div>`);
    root.querySelector("#logoutButton").addEventListener("click",async()=>{try{await api("/logout",{method:"POST"});}catch(_){}setToken(null);window.location.href="index.html";});
  }catch(error){root.innerHTML=`<div class="alert alert-danger">${escapeHtml(error.message)}</div>`;}
}

async function setupTrackOrder(){
  const root=document.getElementById("trackingRoot"); if(!root)return;
  if(!getToken()){window.location.href="login.html";return;}
  const initial=new URLSearchParams(window.location.search).get("order")||"";
  root.innerHTML=`<div class="mb-4"><h2 class="h4">Track an Order</h2><p class="text-muted">Enter your Northstar order ID to see the latest status.</p><form id="trackForm" class="row g-2"><div class="col-md-8"><input class="form-control" name="order_number" value="${escapeHtml(initial)}" placeholder="e.g. NS260816123456AB" required></div><div class="col-md-4"><button class="btn btn-black w-100" type="submit">Track Order</button></div></form></div><div id="trackResult"></div>`;
  const form=root.querySelector("#trackForm"), result=root.querySelector("#trackResult");
  async function load(number){
    if(!number){result.innerHTML="";return;}
    result.innerHTML=`<div class="text-muted">Loading order...</div>`;
    try{
      const data=await api(`/orders/${encodeURIComponent(number.trim())}`);
      const statuses=["Order Placed","Payment Confirmed","Processing","Packed","Handed to Courier","In Transit","Arrived at Local Hub","Out for Delivery","Delivered"];
      const currentIndex=statuses.indexOf(data.order.status);
      const cancelled=data.order.status==="Cancelled";
      const historyMap={};
      data.history.forEach(h=>{historyMap[h.status]=h;});
      const timeline=statuses.map((status,i)=>{
        const reached=!cancelled && i<=currentIndex;
        const event=historyMap[status];
        return `<div class="tracking-step ${reached?"done":""}"><div class="tracking-dot">${reached?"✓":""}</div><div><strong>${status}</strong>${event?`<small>${escapeHtml(event.notes||"")} · ${new Date(event.created_at).toLocaleString()}</small>`:`<small>Pending</small>`}</div></div>`;
      }).join("");
      const currentText=cancelled?"Cancelled":data.order.status;
      const eta=data.order.estimated_delivery_date?new Date(`${data.order.estimated_delivery_date}T00:00:00`).toLocaleDateString("en-KE",{day:"numeric",month:"long",year:"numeric"}):"Being calculated";
      result.innerHTML=`<div class="border rounded p-4 mb-4"><div class="d-flex justify-content-between align-items-center flex-wrap mb-3"><div><h3 class="h5 mb-1">Order ${escapeHtml(data.order.order_number)}</h3><p class="mb-1 text-muted">Current status: <strong>${escapeHtml(currentText)}</strong></p><p class="mb-0 text-muted">Tracking number: <strong>${escapeHtml(data.order.tracking_number||"Not assigned")}</strong></p></div><a href="account.html#orders" class="btn btn-outline-black">My Orders</a></div><div class="row g-3 mb-4"><div class="col-md-6"><div class="bg-light rounded p-3"><small class="text-muted d-block">Estimated delivery</small><strong>${escapeHtml(eta)}</strong></div></div><div class="col-md-6"><div class="bg-light rounded p-3"><small class="text-muted d-block">Tracking</small><strong>Automatic logistics updates</strong></div></div></div>${cancelled?`<div class="alert alert-warning">This order has been cancelled. Please contact Northstar support if you need help.</div>`:""}<div>${timeline}</div></div><div class="border rounded p-4"><h3 class="h5 text-black">Order Items</h3>${data.items.map(i=>`<div class="d-flex justify-content-between border-bottom py-2"><span>${escapeHtml(i.product_name)} × ${i.quantity}</span><strong>${money(i.line_total)}</strong></div>`).join("")}<div class="d-flex justify-content-between pt-3"><strong>Total</strong><strong>${money(data.order.total_amount)}</strong></div></div>`;
    }catch(error){result.innerHTML=`<div class="alert alert-danger">${escapeHtml(error.message)}</div>`;}
  }
  form.addEventListener("submit",e=>{e.preventDefault();load(form.order_number.value);});
  if(initial) load(initial);
  let refreshTimer=null;
  const startAutoRefresh=()=>{ if(refreshTimer) clearInterval(refreshTimer); if(initial) refreshTimer=setInterval(()=>load(initial),60000); };
  startAutoRefresh();
}

async function setupReturns(){
  const root=document.getElementById("returnRoot"); if(!root)return;
  if(!getToken()){window.location.href="login.html";return;}
  const number=new URLSearchParams(window.location.search).get("order")||"";
  root.innerHTML=`<div class="border rounded p-4"><h2 class="h4 mb-3">Return / Refund Request</h2><p class="text-muted">Returns and refunds are reviewed before approval. Orders normally need to be delivered first.</p><form id="returnForm"><div class="mb-3"><label class="form-label">Order Number</label><input class="form-control" name="order_number" value="${escapeHtml(number)}" placeholder="Enter your order ID" required></div><div class="mb-3"><label class="form-label">Reason</label><select class="form-select" name="reason" required><option value="">Select a reason</option><option>Damaged item</option><option>Wrong item received</option><option>Item not as expected</option><option>Other</option></select></div><div class="mb-3"><label class="form-label">Additional details</label><textarea class="form-control" name="description" rows="4" placeholder="Tell us what happened"></textarea></div><button class="btn btn-black" type="submit">Submit Request</button></form></div><div class="mt-4"><h3 class="h5">My Return / Refund Requests</h3><div id="returnsList"></div></div>`;
  const form=root.querySelector("#returnForm");
  form.addEventListener("submit",async e=>{e.preventDefault();const button=form.querySelector("button[type=submit]");button.disabled=true;try{await api("/returns",{method:"POST",body:JSON.stringify({order_number:form.order_number.value,reason:form.reason.value,description:form.description.value})});alert("Your return/refund request has been submitted.");await loadReturns();}catch(error){alert(error.message);}finally{button.disabled=false;}});
  async function loadReturns(){try{const data=await api("/returns");root.querySelector("#returnsList").innerHTML=data.returns.length?data.returns.map(r=>`<div class="border rounded p-3 mb-2"><strong>${escapeHtml(r.order_number)}</strong> — <span class="badge bg-secondary">${escapeHtml(r.status)}</span><div class="small text-muted">${escapeHtml(r.reason)}</div></div>`).join(""):"<p class=\"text-muted\">No return/refund requests yet.</p>";}catch(error){root.querySelector("#returnsList").innerHTML=`<div class="alert alert-danger">${escapeHtml(error.message)}</div>`;}}
  loadReturns();
}

function setupChatbot(){
  if(document.getElementById("northstarChatbot"))return;
  const wrapper=document.createElement("div"); wrapper.id="northstarChatbot";
  wrapper.innerHTML=`<button id="chatToggle" class="northstar-chat-toggle" aria-label="Open Northstar Assistant"><span>💬</span></button><div id="chatPanel" class="northstar-chat-panel" hidden><div class="northstar-chat-header"><div><strong>Northstar Assistant</strong><small>Here to help</small></div><button id="chatClose" type="button" aria-label="Close chat">×</button></div><div id="chatMessages" class="northstar-chat-messages"><div class="chat-message bot">Hi! I can help with products, your cart, orders, tracking, delivery, and returns.</div></div><div class="northstar-chat-quick"><button data-chat="What products do you have?">Products</button><button data-chat="How do I track my order?">Track</button><button data-chat="How do returns and refunds work?">Returns</button></div><form id="chatForm" class="northstar-chat-form"><input id="chatInput" autocomplete="off" placeholder="Type a message..." aria-label="Chat message"><button type="submit" aria-label="Send">Send</button></form></div>`;
  document.body.appendChild(wrapper);
  const panel=wrapper.querySelector("#chatPanel"), messages=wrapper.querySelector("#chatMessages"), input=wrapper.querySelector("#chatInput");
  const addMessage=(text,type)=>{const div=document.createElement("div");div.className=`chat-message ${type}`;div.textContent=text;messages.appendChild(div);messages.scrollTop=messages.scrollHeight;};
  async function sendMessage(text){if(!text.trim())return;addMessage(text,"user");input.value="";try{const data=await api("/chat",{method:"POST",body:JSON.stringify({message:text})});addMessage(data.reply,"bot");if(data.action==="track"&&data.order_number) window.setTimeout(()=>{window.location.href=`track-order.html?order=${encodeURIComponent(data.order_number)}`;},700);}catch(error){addMessage(error.message,"bot");}}
  wrapper.querySelector("#chatToggle").addEventListener("click",()=>{panel.hidden=!panel.hidden;if(!panel.hidden)input.focus();});
  wrapper.querySelector("#chatClose").addEventListener("click",()=>{panel.hidden=true;});
  wrapper.querySelector("#chatForm").addEventListener("submit",e=>{e.preventDefault();sendMessage(input.value);});
  wrapper.querySelectorAll("[data-chat]").forEach(b=>b.addEventListener("click",()=>sendMessage(b.dataset.chat)));
}

document.addEventListener("DOMContentLoaded",()=>{
  updateAccountLink();
  const tools=document.getElementById("customerTools"); if(tools) tools.innerHTML=customerToolsNav("cart");
  const trackTools=document.getElementById("trackTools"); if(trackTools) trackTools.innerHTML=customerToolsNav("track");
  const returnTools=document.getElementById("returnTools"); if(returnTools) returnTools.innerHTML=customerToolsNav("returns");
  const accountTools=document.getElementById("accountTools"); if(accountTools) accountTools.innerHTML=customerToolsNav("orders");
  updateCartCount();setupShop();renderCart();setupLogin();setupRegister();setupCheckout();setupAccount();setupTrackOrder();setupReturns();setupChatbot();
});
