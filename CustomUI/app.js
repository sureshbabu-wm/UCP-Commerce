// Product Data
const products = [
    {
        id: "speedrun_x1",
        name: "SpeedRun X1",
        merchant: "Sportify",
        price: "$129.99",
        stockStatus: "In Stock",
        stockColor: "primary",
        imageUrl: "https://lh3.googleusercontent.com/aida-public/AB6AXuAXC9ckMCAqDmUftd3RDbEkDU-3Uq9LDj1OX0Mv9hO3OP_2-pUaIJyc7JxcgnFctngky8yY6NHNSkqP0_06v5rCeHFrX2O4rYNxdkaYkBUDWXUeTATRbS_nNkxorxslLWYsqpCx34OeC4tq-yu82KjpzW6t2a2Xhj2DkHr57ni3S1LYgJ-a2O2jqJV-WKlFD67HUdetKwd6pFidCl93CQ0tba0UovFfkvzlqa5DAbf2mbh7iyvc2KJysVIldvS1x-D0jXzyl-rBhuIc"
    },
    {
        id: "trailblazer_pro",
        name: "TrailBlazer Pro",
        merchant: "OutdoorGear",
        price: "$145.00",
        stockStatus: "2 left",
        stockColor: "tertiary",
        imageUrl: "https://lh3.googleusercontent.com/aida-public/AB6AXuCuPBdkjUPgBxlGW-KkxNwah23kk6WLbEeKLTIC7lRRJPUpkmLsHv_OTPXJ6nuDSASRbH4zaAN-rbDICtfnZkKd5JXmlAT2qZ_DynBoGiGBrEIS8AS7WDfKPeBz1wmQnwww0XfWjrpSN9lWHPKKz8YGkS7NNpV2RPsZflrA110G2p52y1xi0S3oJYuC2WY7b2cnWEiNxh1yH3G2CrIfL1q3e-eNV5_ITMrsVyb0p1SQpVfZObcB85hlLx-p6Njfrry8u_mJwUUt1B9T"
    }
];

// App State
let currentStep = 0; // 0: Offers, 1: Selected, 2: Plan Approved, 3: Payment Authorized

// Initialize App
document.addEventListener("DOMContentLoaded", () => {
    renderOffers();
});

// Render dynamic offers inside chat stream
function renderOffers() {
    const grid = document.getElementById("offers-grid");
    grid.innerHTML = "";

    products.forEach(p => {
        const itemHtml = `
            <div class="p-4 border border-outline-variant rounded-lg flex flex-col gap-2 bg-surface-container-lowest">
                <div class="flex justify-between items-start">
                    <div>
                        <h4 class="font-headline-sm text-primary font-bold text-base md:text-lg">${p.name}</h4>
                        <p class="font-body-sm text-outline">Merchant: ${p.merchant}</p>
                    </div>
                    <span class="bg-${p.stockColor}/10 text-${p.stockColor} px-2 py-0.5 rounded text-label-caps font-label-caps text-[10px]">${p.stockStatus}</span>
                </div>
                <div class="mt-2 font-data-mono text-data-mono text-on-background text-lg font-bold">${p.price}</div>
                <div class="flex gap-2 mt-4">
                    <button onclick="selectProduct('${p.id}')" class="flex-1 bg-primary text-on-primary py-2 rounded-lg font-body-sm font-semibold active:scale-95 transition-transform">Select</button>
                    <button class="flex-1 border border-outline-variant text-on-surface py-2 rounded-lg font-body-sm active:scale-95 transition-transform hover:bg-surface-container-low">Compare</button>
                </div>
            </div>
        `;
        grid.insertAdjacentHTML("beforeend", itemHtml);
    });
}

// Dynamic flow state machine triggers
function selectProduct(productId) {
    if (currentStep > 0) return; // Prevent double trigger
    currentStep = 1;



    const stepsContainer = document.getElementById("checkout-steps");
    const product = products.find(p => p.id === productId);

    // 1. Append User selection message
    const userMsg = `
        <div class="flex justify-end w-full slide-up">
            <div class="max-w-[80%] bg-surface-container-low rounded-xl px-4 py-3 border border-outline-variant/30">
                <p class="font-body-lg text-on-surface-variant">Select the ${product.name}</p>
            </div>
        </div>
    `;
    stepsContainer.insertAdjacentHTML("beforeend", userMsg);
    scrollToBottom();

    // 2. Append Purchase Plan
    setTimeout(() => {
        const planHtml = `
            <div class="flex justify-start w-full slide-up" id="purchase-plan-step">
                <div class="max-w-[90%] w-full bg-surface-container-lowest border border-outline-variant rounded-lg action-card overflow-hidden">
                    <div class="px-4 py-3 border-b border-outline-variant bg-surface-container-lowest">
                        <h3 class="font-headline-sm text-headline-sm text-on-background font-bold">Purchase Plan</h3>
                    </div>
                    <div class="p-4 space-y-4">
                        <div class="flex items-center justify-between">
                            <div class="flex items-center gap-4">
                                <div class="w-12 h-12 bg-surface-variant rounded-lg flex items-center justify-center">
                                    <span class="material-symbols-outlined text-primary text-2xl">shopping_bag</span>
                                </div>
                                <div>
                                    <p class="font-headline-sm text-on-background font-semibold">${product.name}</p>
                                    <p class="font-body-sm text-outline">${product.merchant} • ${product.price}</p>
                                </div>
                            </div>
                            <span class="bg-${product.stockColor}/10 text-${product.stockColor} px-2 py-1 rounded text-label-caps font-label-caps text-[10px]">${product.stockStatus}</span>
                        </div>
                        <div class="flex gap-3">
                            <button onclick="approvePlan('${product.id}')" class="flex-1 bg-primary text-on-primary py-3 rounded-lg font-body-lg font-semibold active:scale-95 transition-transform">Approve Plan</button>
                            <button class="flex-1 border border-outline-variant text-on-surface py-3 rounded-lg font-body-lg active:scale-95 transition-transform hover:bg-surface-container-low">Modify Selection</button>
                        </div>
                    </div>
                </div>
            </div>
        `;
        stepsContainer.insertAdjacentHTML("beforeend", planHtml);
        scrollToBottom();
    }, 800);
}

function approvePlan(productId) {
    if (currentStep > 1) return;
    currentStep = 2;

    const stepsContainer = document.getElementById("checkout-steps");
    const product = products.find(p => p.id === productId);

    // Render Payment Request Card
    setTimeout(() => {
        const paymentHtml = `
            <div class="flex justify-start w-full slide-up" id="payment-step">
                <div class="max-w-[90%] w-full bg-surface-container-lowest border border-outline-variant rounded-lg action-card overflow-hidden">
                    <div class="px-4 py-3 border-b border-outline-variant bg-surface-container-lowest">
                        <h3 class="font-headline-sm text-headline-sm text-on-background font-bold">Payment Request</h3>
                    </div>
                    <div class="p-4">
                        <div class="bg-surface-container-high rounded-lg p-4 mb-4 grid grid-cols-2 gap-y-4">
                            <div>
                                <p class="font-label-caps text-label-caps text-outline uppercase text-[10px]">Merchant</p>
                                <p class="font-body-lg text-on-background font-semibold">${product.merchant}</p>
                            </div>
                            <div class="text-right">
                                <p class="font-label-caps text-label-caps text-outline uppercase text-[10px]">Total Amount</p>
                                <p class="font-data-mono text-data-mono text-primary font-bold text-lg">${product.price}</p>
                            </div>
                            <div>
                                <p class="font-label-caps text-label-caps text-outline uppercase text-[10px]">Status</p>
                                <div class="flex items-center gap-2 mt-1" id="payment-status-container">
                                    <span class="w-2 h-2 rounded-full bg-tertiary animate-pulse"></span>
                                    <p class="font-body-sm text-tertiary font-medium">Pending Authorization</p>
                                </div>
                            </div>
                        </div>
                        <div class="flex gap-3">
                            <button id="authorize-btn" onclick="authorizePayment('${product.id}')" class="flex-1 bg-on-background text-on-primary py-3 rounded-lg font-body-lg font-semibold flex items-center justify-center gap-2 active:scale-95 transition-transform hover:opacity-90">
                                <span class="material-symbols-outlined text-base">lock</span>
                                Authorize Payment
                            </button>
                            <button class="px-6 border border-outline-variant text-on-surface py-3 rounded-lg font-body-lg active:scale-95 transition-transform hover:bg-surface-container-low">Cancel</button>
                        </div>
                    </div>
                </div>
            </div>
        `;
        stepsContainer.insertAdjacentHTML("beforeend", paymentHtml);
        scrollToBottom();
    }, 600);
}

function authorizePayment(productId) {
    if (currentStep > 2) return;
    currentStep = 3;

    const btn = document.getElementById("authorize-btn");
    const product = products.find(p => p.id === productId);

    // Show loading spinner on payment button
    btn.innerHTML = `
        <svg class="animate-spin h-5 w-5 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
        </svg>
        <span>Securing Transaction...</span>
    `;
    btn.disabled = true;

    // Simulate merchant processing response
    setTimeout(() => {
        // Update payment request status to Authorized
        const statusContainer = document.getElementById("payment-status-container");
        statusContainer.innerHTML = `
            <span class="w-2 h-2 rounded-full bg-green-600"></span>
            <p class="font-body-sm text-green-600 font-medium">Payment Completed</p>
        `;

        const stepsContainer = document.getElementById("checkout-steps");
        const orderHtml = `
            <div class="flex justify-start w-full slide-up" id="order-confirm-step">
                <div class="max-w-[90%] w-full bg-surface-container-lowest border border-outline-variant rounded-lg action-card overflow-hidden">
                    <div class="px-4 py-3 border-b border-outline-variant flex items-center justify-between bg-surface-container-lowest">
                        <h3 class="font-headline-sm text-headline-sm text-on-background font-bold">Order Confirmation</h3>
                        <span class="material-symbols-outlined text-green-600 font-bold text-2xl">check_circle</span>
                    </div>
                    <div class="p-4 grid grid-cols-1 md:grid-cols-3 gap-4">
                        <div>
                            <p class="font-label-caps text-label-caps text-outline uppercase text-[10px]">Order ID</p>
                            <p class="font-data-mono text-data-mono text-on-background font-bold">#UCP-8842</p>
                        </div>
                        <div>
                            <p class="font-label-caps text-label-caps text-outline uppercase text-[10px]">Merchant</p>
                            <p class="font-body-lg text-on-background font-semibold">${product.merchant}</p>
                        </div>
                        <div>
                            <p class="font-label-caps text-label-caps text-outline uppercase text-[10px]">Status</p>
                            <p class="font-body-lg text-green-600 font-bold">Success</p>
                        </div>
                    </div>
                </div>
            </div>
        `;
        stepsContainer.insertAdjacentHTML("beforeend", orderHtml);
        scrollToBottom();
    }, 1500);
}

// User composer message handling
function handleSendMessage() {
    const input = document.getElementById("chat-input");
    const text = input.value.trim();
    if (!text) return;

    input.value = "";
    const stepsContainer = document.getElementById("checkout-steps");

    // Add user message
    const userMsg = `
        <div class="flex justify-end w-full slide-up">
            <div class="max-w-[80%] bg-surface-container-low rounded-xl px-4 py-3 border border-outline-variant/30">
                <p class="font-body-lg text-on-surface-variant">${text}</p>
            </div>
        </div>
    `;
    stepsContainer.insertAdjacentHTML("beforeend", userMsg);
    scrollToBottom();

    // Simulated reply
    setTimeout(() => {
        let replyText = "I can assist you with running shoes under $150. Please click **Select** on one of the products above to trigger the UCP agent transaction checkout flow.";

        if (currentStep === 1) {
            replyText = "Please click **Approve Plan** on the purchase card above to confirm details and shipping info.";
        } else if (currentStep === 2) {
            replyText = "Please authorize the payment request by clicking **Authorize Payment** above.";
        } else if (currentStep === 3) {
            replyText = "Your order #UCP-8842 has been successfully completed! Let me know if you need help with tracking or post-purchase support.";
        }

        const assistantMsg = `
            <div class="flex justify-start w-full slide-up">
                <div class="max-w-[80%] bg-surface-container-lowest rounded-xl px-4 py-3 border border-outline-variant">
                    <p class="font-body-lg text-on-surface">${replyText}</p>
                </div>
            </div>
        `;
        stepsContainer.insertAdjacentHTML("beforeend", assistantMsg);
        scrollToBottom();
    }, 800);
}

// Helpers
function handleTextareaKeydown(event) {
    if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        handleSendMessage();
    }
}

function scrollToBottom() {
    window.scrollTo({
        top: document.body.scrollHeight,
        behavior: 'smooth'
    });
}
