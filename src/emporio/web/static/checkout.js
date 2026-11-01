// Checkout: Enter no campo de CEP recalcula os valores em vez de registrar o pedido sem querer.
document.addEventListener("keydown", function (e) {
  if (e.key !== "Enter" || !e.target || e.target.id !== "cep") return;
  e.preventDefault();
  e.target.dispatchEvent(new Event("change", { bubbles: true }));
});
