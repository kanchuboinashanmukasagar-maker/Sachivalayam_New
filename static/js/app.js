// Client-side interactions for Sachivalayam Portal

document.addEventListener('DOMContentLoaded', () => {
    // Auto-dismiss alert messages after 6 seconds
    setTimeout(() => {
        const alerts = document.querySelectorAll('.flash-alert');
        alerts.forEach(el => {
            el.style.opacity = '0';
            setTimeout(() => el.remove(), 400);
        });
    }, 6000);
});

// Dynamic form field toggling for certificates
function toggleCertFields(prefix) {
    const certType = document.getElementById(prefix + '_cert_type').value;
    const incomeField = document.getElementById(prefix + '_income_field');
    const casteField = document.getElementById(prefix + '_caste_field');

    if (incomeField) {
        if (certType.includes('Income')) {
            incomeField.classList.remove('hidden');
        } else {
            incomeField.classList.add('hidden');
        }
    }

    if (casteField) {
        if (certType.includes('Caste')) {
            casteField.classList.remove('hidden');
        } else {
            casteField.classList.add('hidden');
        }
    }
}
