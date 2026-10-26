/* Protect answers while HTMX saves; no client-side documentary decisions. */
(() => {
  const workspace = document.getElementById('analysis-workspace');
  if (!workspace) return;
  const dirty = new Set();
  const inFlight = new Set();
  const versions = new WeakMap();
  const sent = new WeakMap();
  const updateConclude = () => workspace.querySelectorAll('[data-conclude]').forEach(button => {
    button.disabled = inFlight.size > 0;
    button.title = inFlight.size ? 'Aguarde o salvamento das respostas.' : '';
  });
  const markDirty = event => {
    const form = event.target.closest('.check-form');
    if (!form) return;
    dirty.add(form);
    versions.set(form, (versions.get(form) || 0) + 1);
  };
  workspace.addEventListener('input', markDirty, true);
  workspace.addEventListener('change', markDirty, true);
  workspace.addEventListener('submit', event => {
    if (event.target.querySelector('[data-conclude]') && inFlight.size) {
      event.preventDefault();
      event.stopImmediatePropagation();
    }
  }, true);
  document.body.addEventListener('htmx:beforeRequest', event => {
    const form = event.detail.elt.closest('.check-form');
    if (form) {
      inFlight.add(event.detail.xhr);
      sent.set(event.detail.xhr, {form, version: versions.get(form)});
      updateConclude();
    }
  });
  const finalizeRequest = event => {
    const xhr = event.detail && event.detail.xhr;
    if (xhr) inFlight.delete(xhr);
    const pending = xhr ? sent.get(xhr) : null;
    if (!pending) {
      updateConclude();
      return;
    }
    const invalidFields = JSON.parse((xhr.getResponseHeader && xhr.getResponseHeader('X-Draft-Invalid-Fields')) || '[]');
    Array.from(pending.form.elements).forEach(field => {
      if (invalidFields.includes(field.name)) field.setAttribute('aria-invalid', 'true');
      else field.removeAttribute('aria-invalid');
    });
    if (versions.get(pending.form) === pending.version) dirty.delete(pending.form);
    if (!event.detail.successful) {
      const summary = document.getElementById('analysis-summary');
      if (summary) {
        const alert = document.createElement('p');
        alert.setAttribute('role', 'alert');
        alert.textContent = 'Não foi possível salvar. Tente Salvar item antes de sair.';
        summary.appendChild(alert);
      }
    }
    updateConclude();
  };
  document.body.addEventListener('htmx:afterRequest', finalizeRequest);
  document.body.addEventListener('htmx:sendError', finalizeRequest);
  document.body.addEventListener('htmx:responseError', finalizeRequest);
  document.body.addEventListener('htmx:afterSwap', updateConclude);
  window.addEventListener('beforeunload', event => {
    if (dirty.size || inFlight.size) {event.preventDefault(); event.returnValue = '';}
  });
})();
