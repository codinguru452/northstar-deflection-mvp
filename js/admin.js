const ADMIN_API = "/api";
function getAdminToken(){return localStorage.getItem("northstar_admin_token");}
function setAdminToken(token){token?localStorage.setItem("northstar_admin_token",token):localStorage.removeItem("northstar_admin_token");}
function adminEscape(v){return String(v??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"}[c]));}
async function adminApi(path, options={}){
  const headers={...(options.headers||{})};
  if(options.body && !headers["Content-Type"]) headers["Content-Type"]="application/json";
  const token=getAdminToken(); if(token) headers.Authorization=`Bearer ${token}`;
  const res=await fetch(`${ADMIN_API}${path}`,{...options,headers});
  const data=await res.json().catch(()=>({}));
  if(!res.ok){if(res.status===401)setAdminToken(null);throw new Error(data.error||"Something went wrong.");}
  return data;
}
function statusOptions(current){
  const statuses=["Order Placed","Payment Confirmed","Processing","Packed","Handed to Courier","In Transit","Arrived at Local Hub","Out for Delivery","Delivered","Cancelled"];
  return statuses.map(s=>`<option value="${adminEscape(s)}" ${s===current?"selected":""}>${adminEscape(s)}</option>`).join("");
}
async function loadAdminOrders(){
  const root=document.getElementById("adminOrders");
  if(!root)return;
  try{
    const data=await adminApi("/admin/orders");
    if(!data.orders.length){root.innerHTML='<div class="alert alert-info">No customer orders have been placed yet.</div>';return;}
    root.innerHTML=data.orders.map(o=>`<div class="admin-order-card border rounded p-4 mb-3">
      <div class="d-flex justify-content-between align-items-start flex-wrap gap-2">
        <div><h3 class="h5 mb-1">${adminEscape(o.order_number)}</h3><div class="text-muted small">${adminEscape(o.full_name)} · ${adminEscape(o.email)} · ${adminEscape(o.phone)}</div></div>
        <span class="badge bg-secondary">${adminEscape(o.status)}</span>
      </div>
      <div class="row mt-3 g-3">
        <div class="col-md-4"><strong>Total</strong><div>KSh ${Number(o.total_amount).toLocaleString("en-KE",{maximumFractionDigits:0})}</div></div>
        <div class="col-md-8"><strong>Delivery address</strong><div>${adminEscape(o.delivery_address)}</div></div>
      </div>
      <div class="small text-muted mt-2">Tracking: <strong>${adminEscape(o.tracking_number||"Not assigned")}</strong> · Estimated delivery: ${o.estimated_delivery_date?new Date(`${o.estimated_delivery_date}T00:00:00`).toLocaleDateString("en-KE",{day:"numeric",month:"short",year:"numeric"}):"Not set"}</div><div class="small text-muted">Placed: ${new Date(o.created_at).toLocaleString()} · Last update: ${new Date(o.updated_at).toLocaleString()}</div>
      <form class="admin-status-form mt-3" data-order="${adminEscape(o.order_number)}">
        <div class="row g-2 align-items-end">
          <div class="col-md-4"><label class="form-label">Update status</label><select name="status" class="form-select">${statusOptions(o.status)}</select></div>
          <div class="col-md-6"><label class="form-label">Tracking note</label><input name="notes" class="form-control" placeholder="e.g. Order is now with the delivery team."></div>
          <div class="col-md-2"><button class="btn btn-black w-100" type="submit">Update</button></div>
        </div>
      </form>
    </div>`).join("");
    root.querySelectorAll(".admin-status-form").forEach(form=>form.addEventListener("submit",async e=>{
      e.preventDefault();
      const button=form.querySelector("button");button.disabled=true;
      try{
        await adminApi("/admin/orders/status",{method:"POST",body:JSON.stringify({order_number:form.dataset.order,status:form.status.value,notes:form.notes.value})});
        showAdminToast("Order tracking updated.");
        await loadAdminOrders();
      }catch(err){showAdminToast(err.message,true);}finally{button.disabled=false;}
    }));
  }catch(err){root.innerHTML=`<div class="alert alert-danger">${adminEscape(err.message)}</div>`;}
}
function showAdminToast(message,error=false){
  let el=document.getElementById("adminToast");if(!el){el=document.createElement("div");el.id="adminToast";el.className="northstar-toast";document.body.appendChild(el);}
  el.textContent=message;el.classList.toggle("error",error);el.classList.add("show");clearTimeout(window.adminToastTimer);window.adminToastTimer=setTimeout(()=>el.classList.remove("show"),2200);
}
async function setupAdmin(){
  const login=document.getElementById("adminLogin"), dashboard=document.getElementById("adminDashboard");
  if(!login||!dashboard)return;
  if(getAdminToken()){
    try{const me=await adminApi("/admin/me");showDashboard(me.admin);}catch(_){showLogin();}
  }else showLogin();
  function showLogin(){login.hidden=false;dashboard.hidden=true;}
  function showDashboard(admin){
    login.hidden=true;dashboard.hidden=false;
    document.getElementById("adminName").textContent=admin.full_name;
    loadAdminOrders();
  }
  login.querySelector("form").addEventListener("submit",async e=>{
    e.preventDefault();const button=e.currentTarget.querySelector("button");button.disabled=true;
    try{const data=await adminApi("/admin/login",{method:"POST",body:JSON.stringify({email:e.currentTarget.email.value,password:e.currentTarget.password.value})});setAdminToken(data.token);showDashboard(data.admin);}
    catch(err){showAdminToast(err.message,true);}finally{button.disabled=false;}
  });
  document.getElementById("adminLogout").addEventListener("click",async()=>{try{await adminApi("/admin/logout",{method:"POST"});}catch(_){}setAdminToken(null);showLogin();});
  document.getElementById("adminRefresh").addEventListener("click",loadAdminOrders);
}
document.addEventListener("DOMContentLoaded",setupAdmin);
