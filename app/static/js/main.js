// Main JavaScript file for AI Grader

// Utility functions
const showAlert = (message, type = 'info') => {
    const alertDiv = document.createElement('div');
    alertDiv.className = `alert alert-${type} fade-in`;
    alertDiv.textContent = message;
    
    document.body.insertBefore(alertDiv, document.body.firstChild);
    
    setTimeout(() => {
        alertDiv.remove();
    }, 5000);
};

const showLoading = (show = true) => {
    const overlay = document.getElementById('loadingOverlay');
    if (overlay) {
        if (show) {
            overlay.classList.remove('hidden');
        } else {
            overlay.classList.add('hidden');
        }
    }
};

// API helper functions
const apiRequest = async (url, options = {}) => {
    try {
        const response = await fetch(url, {
            ...options,
            headers: {
                'Content-Type': 'application/json',
                ...options.headers,
            },
        });
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        return await response.json();
    } catch (error) {
        console.error('API request failed:', error);
        throw error;
    }
};

// Form validation
const validateForm = (formId) => {
    const form = document.getElementById(formId);
    if (!form) return false;
    
    const inputs = form.querySelectorAll('input[required], textarea[required]');
    let isValid = true;
    
    inputs.forEach(input => {
        if (!input.value.trim()) {
            input.classList.add('border-red-500');
            isValid = false;
        } else {
            input.classList.remove('border-red-500');
        }
    });
    
    return isValid;
};

// Character counter for textarea
const addCharacterCounter = (textareaId, maxLength = 10000) => {
    const textarea = document.getElementById(textareaId);
    if (!textarea) return;
    
    const counter = document.createElement('div');
    counter.className = 'text-sm text-gray-500 mt-2 text-right';
    counter.dir = 'ltr';
    
    const updateCounter = () => {
        const length = textarea.value.length;
        counter.textContent = `${length} / ${maxLength}`;
        
        if (length > maxLength) {
            counter.classList.add('text-red-500');
        } else {
            counter.classList.remove('text-red-500');
        }
    };
    
    textarea.addEventListener('input', updateCounter);
    textarea.parentNode.appendChild(counter);
    updateCounter();
};

// Smooth scroll to element
const smoothScrollTo = (elementId) => {
    const element = document.getElementById(elementId);
    if (element) {
        element.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
};

// Copy to clipboard
const copyToClipboard = (text) => {
    navigator.clipboard.writeText(text).then(() => {
        showAlert('تم النسخ بنجاح!', 'success');
    }).catch(err => {
        console.error('Failed to copy:', err);
        showAlert('فشل النسخ', 'error');
    });
};

// Initialize tooltips
const initTooltips = () => {
    const tooltips = document.querySelectorAll('[data-tooltip]');
    tooltips.forEach(element => {
        element.addEventListener('mouseenter', (e) => {
            const tooltip = document.createElement('div');
            tooltip.className = 'absolute bg-gray-800 text-white text-sm px-3 py-2 rounded shadow-lg z-50';
            tooltip.textContent = e.target.dataset.tooltip;
            tooltip.style.top = `${e.target.offsetTop - 40}px`;
            tooltip.style.left = `${e.target.offsetLeft}px`;
            tooltip.id = 'tooltip';
            
            document.body.appendChild(tooltip);
        });
        
        element.addEventListener('mouseleave', () => {
            const tooltip = document.getElementById('tooltip');
            if (tooltip) {
                tooltip.remove();
            }
        });
    });
};

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    // Add fade-in animation to main content
    const mainContent = document.querySelector('main');
    if (mainContent) {
        mainContent.classList.add('fade-in');
    }
    
    // Initialize tooltips
    initTooltips();
    
    // Add character counter to submission text
    if (document.getElementById('submissionText')) {
        addCharacterCounter('submissionText');
    }
    
    // Handle back button
    window.addEventListener('popstate', () => {
        showLoading(false);
    });
});

async function downloadReportFile(url, fallbackName) {
    try {
        showLoading(true);
        const response = await fetch(url, { credentials: 'same-origin' });
        const contentType = (response.headers.get('content-type') || '').toLowerCase();

        if (!response.ok) {
            let message = 'تعذّر تحميل الملف.';
            if (contentType.includes('application/json')) {
                try {
                    const data = await response.json();
                    message = data.detail || data.message || data.error || message;
                } catch (_) { /* ignore */ }
            }
            showAlert(message, 'error');
            return;
        }

        if (contentType.includes('application/json')) {
            showAlert('استجابة غير متوقعة من الخادم — المتوقع ملف Word/PDF.', 'error');
            return;
        }

        const blob = await response.blob();
        let filename = fallbackName || 'report';
        const disposition = response.headers.get('content-disposition') || '';
        const utfMatch = disposition.match(/filename\*=UTF-8''([^;\n]+)/i);
        const asciiMatch = disposition.match(/filename="([^"]+)"/i);
        if (utfMatch) {
            try { filename = decodeURIComponent(utfMatch[1]); } catch (_) { filename = utfMatch[1]; }
        } else if (asciiMatch) {
            filename = asciiMatch[1];
        }

        const objectUrl = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = objectUrl;
        link.download = filename;
        document.body.appendChild(link);
        link.click();
        link.remove();
        URL.revokeObjectURL(objectUrl);
    } catch (err) {
        showAlert('تعذّر تحميل الملف: ' + (err.message || err), 'error');
    } finally {
        showLoading(false);
    }
}

// Export functions for use in other scripts
window.aiGrader = {
    showAlert,
    showLoading,
    apiRequest,
    validateForm,
    copyToClipboard,
    smoothScrollTo,
    downloadReportFile
};
