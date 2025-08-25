/**
 * Edit Account JavaScript
 * Handles form submission and API communication for account management
 */

document.addEventListener('DOMContentLoaded', function() {
    // Get form elements
    const form = document.getElementById('accountForm');
    const phoneInput = document.getElementById('phone');
    const fullnameInput = document.getElementById('fullname');
    const passwordInput = document.getElementById('password');
    const deactivateBtn = document.getElementById('deactivateBtn');
    const deleteBtn = document.getElementById('deleteBtn');
    const responseArea = document.getElementById('responseArea');
    const responseContent = document.getElementById('responseContent');
    
    // Get modal elements
    const confirmationModalElement = document.getElementById('confirmationModal');
    const loadingModalElement = document.getElementById('loadingModal');
    const confirmationMessage = document.getElementById('confirmationMessage');
    const confirmActionBtn = document.getElementById('confirmActionBtn');
    
    // Initialize modals with explicit options
    const confirmationModal = new bootstrap.Modal(confirmationModalElement, {
        backdrop: 'static',
        keyboard: false
    });
    const loadingModal = new bootstrap.Modal(loadingModalElement, {
        backdrop: 'static',
        keyboard: false
    });
    
    let currentAction = null;
    let loadingStartTime = null;
    
    // Emergency cleanup function to handle stuck modals
    function emergencyModalCleanup() {
        const now = Date.now();
        const loadingModalEl = document.getElementById('loadingModal');
        
        // If loading modal has been visible for more than 35 seconds, force close it
        if (loadingStartTime && (now - loadingStartTime > 35000)) {
            console.warn('Emergency: Loading modal stuck for >35s, forcing cleanup...');
            hideLoading();
            loadingStartTime = null;
        }
        
        // Check if there are orphaned modal backdrops
        const backdrops = document.querySelectorAll('.modal-backdrop');
        if (backdrops.length > 0 && !loadingModalEl?.classList.contains('show')) {
            console.warn('Emergency: Found orphaned modal backdrops, removing...');
            backdrops.forEach(backdrop => backdrop.remove());
            document.body.classList.remove('modal-open');
            document.body.style.removeProperty('overflow');
            document.body.style.removeProperty('padding-right');
        }
    }
    
    // Run emergency cleanup every 5 seconds
    setInterval(emergencyModalCleanup, 5000);

    // Form validation
    function validateForm() {
        let isValid = true;
        
        // Clear previous errors
        clearErrors();
        
        // Validate phone
        const phone = phoneInput.value.trim();
        if (!phone) {
            showFieldError('phone', 'Phone number is required');
            isValid = false;
        } else if (!/^[0-9+\-\s()]+$/.test(phone)) {
            showFieldError('phone', 'Please enter a valid phone number');
            isValid = false;
        }
        
        // Validate fullname
        const fullname = fullnameInput.value.trim();
        if (!fullname) {
            showFieldError('fullname', 'Full name is required');
            isValid = false;
        } else if (fullname.length < 2) {
            showFieldError('fullname', 'Full name must be at least 2 characters');
            isValid = false;
        }
        
        // Validate password
        const password = passwordInput.value;
        if (!password) {
            showFieldError('password', 'Password is required');
            isValid = false;
        } else if (password.length < 6) {
            showFieldError('password', 'Password must be at least 6 characters');
            isValid = false;
        }
        
        return isValid;
    }
    
    // Show field error
    function showFieldError(fieldName, message) {
        const field = document.getElementById(fieldName);
        const errorElement = document.getElementById(fieldName + '-error');
        
        field.classList.add('is-invalid', 'shake');
        errorElement.textContent = message;
        
        // Remove shake animation after it completes
        setTimeout(() => {
            field.classList.remove('shake');
        }, 500);
    }
    
    // Clear all errors
    function clearErrors() {
        const fields = ['phone', 'fullname', 'password'];
        fields.forEach(fieldName => {
            const field = document.getElementById(fieldName);
            const errorElement = document.getElementById(fieldName + '-error');
            
            field.classList.remove('is-invalid', 'is-valid');
            errorElement.textContent = '';
        });
    }
    
    // Mark fields as valid
    function markFieldsValid() {
        const fields = ['phone', 'fullname', 'password'];
        fields.forEach(fieldName => {
            const field = document.getElementById(fieldName);
            field.classList.remove('is-invalid');
            field.classList.add('is-valid');
        });
    }
    
    // Show confirmation modal
    function showConfirmation(action) {
        currentAction = action;
        
        let message, buttonClass, buttonText;
        
        if (action === 'deactivate') {
            message = 'Are you sure you want to deactivate your account? You can reactivate it anytime by logging in.';
            buttonClass = 'btn-warning';
            buttonText = 'Deactivate Account';
        } else {
            message = 'Are you sure you want to permanently delete your account? This action cannot be undone and all your data will be lost.';
            buttonClass = 'btn-danger';
            buttonText = 'Delete Account';
        }
        
        confirmationMessage.textContent = message;
        confirmActionBtn.className = `btn ${buttonClass}`;
        confirmActionBtn.textContent = buttonText;
        
        confirmationModal.show();
    }
    
    // Show loading modal
    function showLoading() {
        try {
            loadingStartTime = Date.now();
            loadingModal.show();
            console.log('Loading modal shown at:', new Date(loadingStartTime).toISOString());
        } catch (error) {
            console.error('Error showing loading modal:', error);
        }
    }
    
    // Hide loading modal with aggressive cleanup
    function hideLoading() {
        console.log('Attempting to hide loading modal...');
        
        try {
            // Try Bootstrap modal hide first
            if (loadingModal && typeof loadingModal.hide === 'function') {
                loadingModal.hide();
            }
        } catch (error) {
            console.error('Error with Bootstrap modal hide:', error);
        }
        
        // Force cleanup regardless of Bootstrap modal state
        setTimeout(() => {
            try {
                // Remove all modal backdrops
                const backdrops = document.querySelectorAll('.modal-backdrop');
                console.log(`Found ${backdrops.length} modal backdrops to remove`);
                backdrops.forEach(backdrop => {
                    backdrop.remove();
                });
                
                // Force hide the modal element
                const modalEl = document.getElementById('loadingModal');
                if (modalEl) {
                    modalEl.style.display = 'none';
                    modalEl.classList.remove('show', 'd-block');
                    modalEl.setAttribute('aria-hidden', 'true');
                    modalEl.removeAttribute('aria-modal');
                    modalEl.removeAttribute('role');
                }
                
                // Clean up body classes and styles
                document.body.classList.remove('modal-open');
                document.body.style.removeProperty('overflow');
                document.body.style.removeProperty('padding-right');
                
                console.log('Loading modal cleanup completed');
            } catch (cleanupError) {
                console.error('Error during modal cleanup:', cleanupError);
            }
        }, 50);
        
        // Reset loading timer
        loadingStartTime = null;
    }
    
    // Show response
    function showResponse(response, isSuccess = false) {
        responseContent.textContent = JSON.stringify(response, null, 2);
        responseContent.className = isSuccess ? 'response-success' : 'response-error';
        responseArea.style.display = 'block';
        
        // Scroll to response
        responseArea.scrollIntoView({ behavior: 'smooth' });
    }
    
    // Make API request
    async function makeApiRequest(action) {
        const formData = {
            phone: phoneInput.value.trim(),
            fullname: fullnameInput.value.trim(),
            password: passwordInput.value,
            madrasa_name: null // Will use default from server
        };
        
        try {
            showLoading();
            
            // Create an AbortController for timeout
            const controller = new AbortController();
            const timeoutId = setTimeout(() => {
                console.log('Request timeout reached, aborting...');
                controller.abort();
                hideLoading(); // Force hide loading modal on timeout
            }, 30000); // 30 seconds
            
            const response = await fetch(`/account/${action}`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Accept': 'application/json',
                    'X-API-Key': 'madrasasecretwebkey'
                },
                body: JSON.stringify(formData),
                signal: controller.signal
            });
            
            // Clear timeout if request completes
            clearTimeout(timeoutId);
            
            let responseData;
            try {
                responseData = await response.json();
            } catch (jsonError) {
                console.error('Error parsing JSON response:', jsonError);
                responseData = {
                    error: 'parse_error',
                    message: 'Server returned invalid response',
                    details: jsonError.message
                };
            }
            
            // Always hide loading modal after getting response
            hideLoading();
            
            if (response.ok) {
                showResponse(responseData, true);
                // Optionally clear the form on success
                form.reset();
                clearErrors();
            } else {
                showResponse(responseData, false);
            }
            
        } catch (error) {
            // Always hide loading modal on any error
            hideLoading();
            console.error('API request failed:', error);
            
            let errorResponse;
            
            if (error.name === 'AbortError') {
                // Request was aborted due to timeout
                errorResponse = {
                    error: 'timeout_error',
                    message: 'Request timed out after 30 seconds. The server might be busy or experiencing issues.',
                    details: 'Request aborted due to timeout'
                };
            } else {
                // Other network errors
                errorResponse = {
                    error: 'network_error',
                    message: 'Failed to connect to server. Please check your internet connection and try again.',
                    details: error.message
                };
            }
            
            showResponse(errorResponse, false);
        } finally {
            // Extra safety: ensure loading modal is hidden
            setTimeout(() => {
                hideLoading();
            }, 100);
        }
    }
    
    // Button event handlers
    deactivateBtn.addEventListener('click', function(e) {
        e.preventDefault();
        
        if (!validateForm()) {
            return;
        }
        
        markFieldsValid();
        showConfirmation('deactivate');
    });
    
    deleteBtn.addEventListener('click', function(e) {
        e.preventDefault();
        
        if (!validateForm()) {
            return;
        }
        
        markFieldsValid();
        showConfirmation('delete');
    });
    
    // Confirmation modal confirm button
    confirmActionBtn.addEventListener('click', function() {
        confirmationModal.hide();
        if (currentAction) {
            makeApiRequest(currentAction);
        }
    });
    
    // Real-time validation
    phoneInput.addEventListener('blur', function() {
        const phone = this.value.trim();
        if (phone && !/^[0-9+\-\s()]+$/.test(phone)) {
            showFieldError('phone', 'Please enter a valid phone number');
        } else if (phone) {
            clearErrors();
        }
    });
    
    fullnameInput.addEventListener('blur', function() {
        const fullname = this.value.trim();
        if (fullname && fullname.length < 2) {
            showFieldError('fullname', 'Full name must be at least 2 characters');
        } else if (fullname) {
            clearErrors();
        }
    });
    
    passwordInput.addEventListener('blur', function() {
        const password = this.value;
        if (password && password.length < 6) {
            showFieldError('password', 'Password must be at least 6 characters');
        } else if (password) {
            clearErrors();
        }
    });
    
    // Handle form submit (prevent default)
    form.addEventListener('submit', function(e) {
        e.preventDefault();
    });
    
    // Add input event listeners to clear validation on typing
    [phoneInput, fullnameInput, passwordInput].forEach(input => {
        input.addEventListener('input', function() {
            if (this.classList.contains('is-invalid')) {
                this.classList.remove('is-invalid');
                const errorElement = document.getElementById(this.id + '-error');
                errorElement.textContent = '';
            }
        });
    });
    
    // Keyboard shortcuts
    document.addEventListener('keydown', function(e) {
        // Escape key to close modals
        if (e.key === 'Escape') {
            confirmationModal.hide();
            loadingModal.hide();
        }
        
        // Enter key in password field to trigger deactivate (safer default)
        if (e.key === 'Enter' && document.activeElement === passwordInput) {
            e.preventDefault();
            deactivateBtn.click();
        }
    });
    
    // Focus first input on page load
    phoneInput.focus();
    
    // Hide response area when user starts typing again
    [phoneInput, fullnameInput, passwordInput].forEach(input => {
        input.addEventListener('focus', function() {
            if (responseArea.style.display !== 'none') {
                responseArea.style.display = 'none';
            }
        });
    });
});

// Utility function to format phone number (optional enhancement)
function formatPhoneNumber(value) {
    // Remove all non-numeric characters except +
    const phoneNumber = value.replace(/[^\d+]/g, '');
    
    // Basic formatting for common patterns
    if (phoneNumber.startsWith('+88')) {
        // Bangladesh format
        return phoneNumber.replace(/(\+88)(\d{2})(\d{4})(\d{4})/, '$1 $2 $3 $4');
    } else if (phoneNumber.length === 11 && phoneNumber.startsWith('0')) {
        // Local Bangladesh format
        return phoneNumber.replace(/(\d{2})(\d{4})(\d{5})/, '$1 $2 $3');
    }
    
    return phoneNumber;
}

// Export for potential testing
if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        formatPhoneNumber
    };
}
