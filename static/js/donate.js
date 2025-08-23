// Donate Page JavaScript

document.addEventListener('DOMContentLoaded', () => {
  const modalEl = document.getElementById('donateModal');
  const modal = new bootstrap.Modal(modalEl);
  const qrImg = document.getElementById('modal-qr');
  const infoText = document.getElementById('modal-info');
  const linkBtn = document.getElementById('modal-link');
  const copyBtn = document.getElementById('copy-btn');

  document.querySelectorAll('.option-card').forEach(card => {
    card.addEventListener('click', e => {
      e.preventDefault();
      const title = card.dataset.title;
      const url = card.dataset.url;
      const qr = card.dataset.qr;
      const info = card.dataset.info;
      const gateway = card.dataset.gateway === 'true';

      document.getElementById('donateModalLabel').textContent = title;

      if (qr) {
        qrImg.src = qr;
        qrImg.style.display = '';
      } else {
        qrImg.style.display = 'none';
      }

      infoText.textContent = info;

      if (gateway) {
        linkBtn.classList.remove('d-none');
        linkBtn.onclick = async () => {
          const phone = prompt("Enter your phone number:");
          const fullname = prompt("Enter your full name:");
          const amount = prompt("Enter amount:");

          if (!phone || !fullname || !amount) {
            alert("Please provide all required information!");
            return;
          }

          const payload = {
            phone: phone,
            fullname: fullname,
            amount: amount,
            type: "sslcommerz"
          };

          try {
            const res = await fetch(url, {
              method: 'POST',
              headers: {'Content-Type': 'application/json'},
              body: JSON.stringify(payload)
            });
            const data = await res.json();
            if (data.GatewayPageURL) {
              window.location.href = data.GatewayPageURL;
            } else {
              alert(data.error || "Payment gateway error. Please try again.");
            }
          } catch (err) {
            alert("Could not connect to payments gateway. Please try again later.");
          }
        };
      } else {
        linkBtn.classList.add('d-none');
        linkBtn.onclick = null;
      }

      modal.show();
    });
  });

  copyBtn.addEventListener('click', () => {
    const text = infoText.textContent;
    navigator.clipboard.writeText(text).then(() => {
      copyBtn.textContent = 'Copied!';
      setTimeout(() => copyBtn.textContent = 'Copy Number', 2000);
    });
  });
});
