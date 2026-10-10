import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import {
  createSale,
  errorMessage,
  getCustomers,
  getProducts,
  updateSale,
} from "../services/api";
import type { CustomerOption, ProductOption, Sale } from "../types";
import { preciseMoney } from "../utils/format";

export function SaleForm({
  onClose,
  onSaved,
  sale,
}: {
  onClose: () => void;
  onSaved: () => void;
  sale?: Sale;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const submitting = useRef(false);
  const [customers, setCustomers] = useState<CustomerOption[]>([]);
  const [products, setProducts] = useState<ProductOption[]>([]);
  const [customerId, setCustomerId] = useState(
    sale ? String(sale.customer_id) : "",
  );
  const [productId, setProductId] = useState(
    sale ? String(sale.product_id) : "",
  );
  const [quantity, setQuantity] = useState(sale ? String(sale.quantity) : "1");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [loadError, setLoadError] = useState("");
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);

  useEffect(() => {
    const element = dialog.current!;
    element.showModal();
    return () => element.close();
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setLoadError("");
    Promise.all([
      getCustomers(controller.signal),
      getProducts(controller.signal),
    ])
      .then(([buyers, items]) => {
        if (!controller.signal.aborted) {
          setCustomers(buyers);
          setProducts(items);
        }
      })
      .catch((failure: unknown) => {
        if (!controller.signal.aborted) setLoadError(errorMessage(failure));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [retry]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (submitting.current) return;
    const units = Number(quantity);
    if (
      !customerId ||
      !productId ||
      !Number.isInteger(units) ||
      units <= 0 ||
      units > 2147483647
    ) {
      setError(
        "Select a customer and product, and enter a positive whole-number quantity (up to 2,147,483,647).",
      );
      return;
    }
    submitting.current = true;
    setSaving(true);
    setError("");
    try {
      const request = {
        customer_id: Number(customerId),
        product_id: Number(productId),
        quantity: units,
      };
      if (sale) await updateSale(sale.id, request);
      else await createSale(request);
    } catch (failure: unknown) {
      setError(errorMessage(failure));
      submitting.current = false;
      setSaving(false);
      return;
    }
    onSaved();
  }

  const selectedProduct = products.find(
    (product) => product.id === Number(productId),
  );
  const unavailable =
    loading || !!loadError || !customers.length || !products.length;
  return (
    <dialog
      ref={dialog}
      className="card sale-dialog"
      aria-labelledby="sale-form-title"
      onCancel={(event) => {
        event.preventDefault();
        if (!submitting.current) onClose();
      }}
    >
      <form onSubmit={submit}>
        <h2 id="sale-form-title">
          {sale ? `Edit Sale #${String(sale.id).padStart(4, "0")}` : "Add Sale"}
        </h2>
        {loading && <p role="status">Loading customers and products…</p>}
        {loadError && (
          <div role="alert" className="error-state">
            <p>{loadError}</p>
            <button
              type="button"
              className="button secondary"
              onClick={() => setRetry((value) => value + 1)}
            >
              Retry
            </button>
          </div>
        )}
        {!loading && !loadError && (!customers.length || !products.length) && (
          <p role="status">
            A customer and product must exist before you can save a sale.
          </p>
        )}
        <fieldset disabled={unavailable || saving}>
          <label htmlFor="sale-customer">Customer</label>
          <select
            id="sale-customer"
            required
            value={customerId}
            onChange={(event) => setCustomerId(event.target.value)}
          >
            <option value="">Select a customer</option>
            {customers.map((customer) => (
              <option key={customer.id} value={customer.id}>
                {customer.name}
              </option>
            ))}
          </select>
          <label htmlFor="sale-product">Product</label>
          <select
            id="sale-product"
            required
            value={productId}
            onChange={(event) => setProductId(event.target.value)}
          >
            <option value="">Select a product</option>
            {products.map((product) => (
              <option key={product.id} value={product.id}>
                {product.name}
              </option>
            ))}
          </select>
          {selectedProduct && (
            <p>
              Current unit price:{" "}
              {selectedProduct.price_toman === null
                ? "Toman price unavailable"
                : preciseMoney(selectedProduct.price_toman)}
              {selectedProduct.exchange_rate_stale && " (last known rate)"}
              <br />
              Product or quantity changes use the rate at save time.
              Customer-only edits preserve the recorded total.
            </p>
          )}
          <label htmlFor="sale-quantity">Quantity</label>
          <input
            id="sale-quantity"
            type="number"
            min="1"
            max="2147483647"
            step="1"
            required
            value={quantity}
            onChange={(event) => setQuantity(event.target.value)}
          />
        </fieldset>
        {error && (
          <p role="alert" className="error-state">
            {error}
          </p>
        )}
        <div className="sales-actions">
          <button
            type="button"
            className="button secondary"
            disabled={saving}
            onClick={onClose}
          >
            Cancel
          </button>
          <button
            type="submit"
            className="button"
            disabled={unavailable || saving}
          >
            {saving ? "Saving…" : "Save Sale"}
          </button>
        </div>
      </form>
    </dialog>
  );
}
