class PaymentProcessor {
    constructor() {
        this.html5QrcodeScanner = null;
        this.initializeEventListeners();
    }

    initializeEventListeners() {
        document.addEventListener('DOMContentLoaded', () => {
            this.startScanner();
            this.checkCameraSupport();
            this.initializePaymentForm();
            this.initializeReferenceInput();
        });
    }

    startScanner() {
        const config = {
            fps: 10,
            qrbox: { width: 250, height: 250 },
            aspectRatio: 1.0
        };
        
        this.html5QrcodeScanner = new Html5QrcodeScanner("qr-reader", config);
        this.html5QrcodeScanner.render(this.onScanSuccess.bind(this), this.onScanError.bind(this));
    }

    checkCameraSupport() {
        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
            document.getElementById('camera-error').classList.remove('hidden');
            document.getElementById('qr-reader').style.display = 'none';
        }
    }

    initializePaymentForm() {
        const form = document.getElementById('payment-form');
        if (form) {
            form.addEventListener('submit', this.handlePaymentSubmit.bind(this));
        }
    }

    initializeReferenceInput() {
        const input = document.getElementById('payment-reference');
        if (input) {
            input.addEventListener('input', this.handleReferenceInput.bind(this));
        }
    }

    async onScanSuccess(decodedText) {
        console.log("QR code scanned:", decodedText);
        const reference = this.extractReference(decodedText);
        console.log("Extracted reference:", reference);
        this.html5QrcodeScanner.clear();
        await this.processBookingReference(reference);
    }

    onScanError(error) {
        console.warn(`QR Code scanning failed: ${error}`);
    }

    extractReference(text) {
        console.log("Extracting from:", text);
        
        if (text.includes("/booking/") || text.includes("/payment/")) {
            const urlParts = text.split("/");
            return urlParts[urlParts.length - 1];
        }
        
        if (text.includes("Booking Reference:")) {
            const match = text.match(/Booking Reference: ([^\n]+)/);
            return match?.[1]?.trim() || text;
        }
        
        if (text.includes(":")) {
            return text.split(":").pop().trim();
        }
        
        return text.trim();
    }

    async processBookingReference(reference) {
        this.showLoadingState();
        try {
            const data = await this.fetchBookingDetails(reference);
            if (data.success) {
                this.updateUIWithBookingDetails(data, reference);
            } else {
                throw new Error(data.error || 'Invalid booking reference');
            }
        } catch (error) {
            this.showError(error.message || 'Error processing booking reference');
            this.startScanner();
        }
    }

    async fetchBookingDetails(reference) {
        try {
            console.log("Fetching details for reference:", reference);
            const response = await fetch(`/api/booking-details/${reference}/`);
            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.error || `Request failed with status ${response.status}`);
            }
            const data = await response.json();
            console.log("API response:", data);
            return data;
        } catch (error) {
            console.error("Fetch error:", error);
            throw error;
        }
    }

    updateUIWithBookingDetails(data, reference) {
        // Basic booking information
        const elements = {
            'passenger-name': data.passenger_name,
            'contact-number': data.contact_number,
            'email': data.email,
            'schedule-details': data.schedule,
            'total-amount': `₱${data.total_amount}`,
            'booking-type': data.booking_type,
            'departure-datetime': data.departure_datetime,
            'created-at': data.created_at
        };

        // Add type-specific information
        if (data.booking_type === 'Passenger') {
            elements['passenger-count'] = `${data.number_of_passengers} passenger(s)`;
            if (data.cargo_weight > 0) {
                elements['cargo-details'] = `Cargo: ${data.cargo_weight} tons`;
            }
        } else if (data.booking_type === 'Vehicle') {
            elements['vehicle-details'] = `${data.vehicle_type} (${data.plate_number})`;
            elements['occupant-count'] = `${data.occupant_count} occupant(s)`;
            if (data.cargo_weight > 0) {
                elements['cargo-details'] = `Cargo: ${data.cargo_weight} tons`;
            }
        }

        // Safely update each element
        for (const [id, value] of Object.entries(elements)) {
            const element = document.getElementById(id);
            if (element) {
                element.textContent = value;
            }
        }

        // Show/hide payment status
        const paymentStatus = document.getElementById('payment-status');
        if (paymentStatus) {
            paymentStatus.className = data.is_paid ? 
                'text-green-600 font-semibold' : 
                'text-yellow-600 font-semibold';
            paymentStatus.textContent = data.is_paid ? 'Paid' : 'Pending Payment';
        }

        // Show the booking details container
        const bookingDetails = document.getElementById('booking-details');
        if (bookingDetails) {
            bookingDetails.classList.remove('hidden');
        }

        // Update payment reference input
        const paymentReference = document.getElementById('payment-reference');
        if (paymentReference) {
            paymentReference.value = reference;
        }
    }

    showLoadingState() {
        const bookingDetails = document.getElementById('booking-details');
        if (bookingDetails) {
            bookingDetails.innerHTML = `
                <div class="text-center p-6">
                    <div class="inline-block animate-spin rounded-full h-8 w-8 border-t-2 border-b-2 border-blue-600"></div>
                    <p class="mt-2 text-gray-600">Loading booking details...</p>
                </div>
            `;
            bookingDetails.classList.remove('hidden');
        }
    }

    showError(message) {
        const bookingDetails = document.getElementById('booking-details');
        if (bookingDetails) {
            bookingDetails.innerHTML = `
                <div class="text-center p-6">
                    <div class="text-red-500 mb-2"><i class="fas fa-exclamation-circle text-xl"></i></div>
                    <p class="text-red-600">${message}</p>
                    <p class="mt-2 text-gray-600">Please try scanning again or enter the reference manually.</p>
                </div>
            `;
            bookingDetails.classList.remove('hidden');
        }
    }

    updateQRCodeDisplay(reference) {
        const qrElement = document.getElementById('booking-qr');
        if (qrElement) {
            qrElement.innerHTML = `
                <h3 class="text-lg font-semibold text-gray-800 mb-4">
                    <i class="fas fa-ticket-alt mr-2 text-blue-600"></i>
                    Booking QR Code
                </h3>
                <img src="/generate-qr-code/${reference}/" 
                     alt="Booking QR Code" 
                     class="mx-auto max-w-[200px] mb-4">
                <p class="text-sm text-gray-600 text-center">
                    Reference: ${reference}
                </p>
            `;
        }
    }

    showSuccessMessage(reference) {
        const messageEl = document.createElement('div');
        messageEl.className = 'bg-green-50 border-l-4 border-green-500 text-green-700 p-4 mb-6 rounded-r';
        messageEl.innerHTML = `
            <p class="font-bold">Booking Found</p>
            <p>Successfully retrieved booking details for reference: ${reference}</p>
        `;
        
        const form = document.getElementById('payment-form');
        if (form && form.parentNode) {
            form.parentNode.insertBefore(messageEl, form);
        }
    }

    handleReferenceInput(event) {
        const reference = event.target.value.trim();
        if (reference.length >= 6) {
            this.processBookingReference(reference);
        }
    }
    
    handlePaymentSubmit(event) {
        event.preventDefault();
        
        const reference = document.getElementById('payment-reference').value.trim();
        const paymentMethod = document.querySelector('input[name="payment_method"]:checked')?.value || 'cash';
        
        if (!reference) {
            alert('Please enter a booking reference');
            return;
        }
        
        // Show loading state
        this.showLoadingState();
        
        // Submit the payment data
        fetch('/process-payment/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded',
                'X-CSRFToken': this.getCsrfToken()
            },
            body: `payment_reference=${reference}&payment_method=${paymentMethod}`
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                // Show success message
                const messageEl = document.createElement('div');
                messageEl.className = 'bg-green-50 border-l-4 border-green-500 text-green-700 p-4 mb-6 rounded-r';
                messageEl.innerHTML = `
                    <p class="font-bold">Payment Successful!</p>
                    <p>${data.message}</p>
                `;
                
                const form = document.getElementById('payment-form');
                if (form && form.parentNode) {
                    form.parentNode.insertBefore(messageEl, form);
                }
                
                // Optionally redirect to confirmation page
                setTimeout(() => {
                    window.location.href = `/booking-confirmation/${reference}/`;
                }, 2000);
            } else {
                // Show error message
                this.showError(data.error || 'Error processing payment');
            }
        })
        .catch(error => {
            this.showError('Network error: ' + error.message);
        });
    }

    getCsrfToken() {
        return document.querySelector('input[name="csrfmiddlewaretoken"]')?.value || '';
    }
}

const paymentProcessor = new PaymentProcessor();
