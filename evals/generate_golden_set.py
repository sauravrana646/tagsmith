#!/usr/bin/env python3
"""Generate/refresh evals/golden_set.jsonl (no LLM required).

Produces a diverse, hand-labeled synthetic corpus across the seed taxonomy.
Real inbox labels can still be merged later via `tagsmith eval-export-corrections`.

Usage:
  uv run python evals/generate_golden_set.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tests.fixtures.messages import (  # noqa: E402
    HTML_ONLY,
    NEWSLETTER,
    OTP_CODE,
    PAYMENT_ALERT,
    SECURITY_ALERT,
    WITH_ATTACHMENT,
    _msg,
)

OUT = Path(__file__).resolve().parent / "golden_set.jsonl"


def case(
    *,
    id: str,
    expected_label_key: str | None,
    message: dict[str, Any],
    notes: str = "",
    expected_route: str | None = None,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "id": id,
        "expected_label_key": expected_label_key,
        "notes": notes,
        "message": message,
    }
    if expected_route is not None:
        row["expected_route"] = expected_route
    return row


def build_cases() -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []

    # --- Fixture-derived (keep stable ids) ---
    cases.extend(
        [
            case(
                id="fixture_payment_chase",
                expected_label_key="payment-sent",
                expected_route="apply",
                notes="Chase payment alert — builtin rule",
                message=PAYMENT_ALERT,
            ),
            case(
                id="fixture_security_google",
                expected_label_key="security-alert",
                expected_route="apply",
                notes="Google security alert — builtin rule",
                message=SECURITY_ALERT,
            ),
            case(
                id="fixture_otp_github",
                expected_label_key="otp-verification",
                expected_route="apply",
                notes="GitHub OTP — builtin rule",
                message=OTP_CODE,
            ),
            case(
                id="fixture_newsletter_tldr",
                expected_label_key="newsletter",
                expected_route="apply",
                notes="Newsletter with List-Unsubscribe — builtin rule",
                message=NEWSLETTER,
            ),
            case(
                id="fixture_promo_html",
                expected_label_key="promotion",
                notes="HTML-only flash sale — typically LLM",
                message=HTML_ONLY,
            ),
            case(
                id="fixture_statement_attach",
                expected_label_key="account-statement",
                notes="Account statement with PDF filename only",
                message=WITH_ATTACHMENT,
            ),
        ]
    )

    # --- payment-sent ---
    payment_sent = [
        (
            "chase",
            "Chase Alerts <no.reply.alerts@chase.com>",
            "You paid $18.40 to Starbucks",
            "Card ending in 4242 was charged $18.40 at Starbucks.",
            "apply",
        ),
        (
            "chase2",
            "Chase Alerts <no.reply.alerts@chase.com>",
            "Purchase of $9.99 at APPLE.COM/BILL",
            "A debit purchase posted for $9.99.",
            "apply",
        ),
        (
            "amazonpay",
            "Amazon Pay <no-reply@amazonpay.in>",
            "Rs.249 was paid to Zomato",
            "Rs.249 was paid successfully from Amazon Pay.",
            "apply",
        ),
        (
            "generic_rs",
            "Wallet <noreply@paytm.example>",
            "Rs. 1,500 was paid on 11 Aug",
            "Your payment of Rs. 1,500 was paid on 11 Aug to Electricity Board.",
            "apply",
        ),
        (
            "upi",
            "UPI <alerts@upi.example>",
            "You paid ₹750 to Swiggy",
            "UPI payment of ₹750 to Swiggy succeeded. Ref UPI123.",
            None,
        ),
        (
            "card",
            "Amex <alerts@americanexpress.com>",
            "Your card was charged $64.20",
            "A charge of $64.20 posted to your Amex ending 1005.",
            None,
        ),
    ]
    for slug, sender, subject, body, route in payment_sent:
        cases.append(
            case(
                id=f"gold_payment_sent_{slug}",
                expected_label_key="payment-sent",
                expected_route=route,
                notes=f"payment-sent variant {slug}",
                message=_msg(
                    gmail_id=f"msg_ps_{slug}",
                    thread_id=f"thr_ps_{slug}",
                    sender=sender,
                    to="user@example.com",
                    subject=subject,
                    date="Mon, 11 Aug 2025 09:00:00 +0000",
                    body_plain=body,
                ),
            )
        )

    # --- payment-received ---
    payment_recv = [
        (
            "chase",
            "Chase Alerts <no.reply.alerts@chase.com>",
            "You received a direct deposit of $3,100.00",
            "Payment received. Amount $3,100.00 from ACME PAYROLL.",
            "apply",
        ),
        (
            "chase2",
            "Chase Alerts <no.reply.alerts@chase.com>",
            "Deposit posted: $50.00",
            "A credit posted to your account for $50.00.",
            "apply",
        ),
        (
            "venmo",
            "Venmo <venmo@venmo.com>",
            "Alex paid you $25.00",
            "You received $25.00 from Alex for dinner.",
            None,
        ),
        (
            "wire",
            "Bank Wire <alerts@wellsfargo.com>",
            "Incoming wire transfer credited",
            "An incoming wire of $12,000 was credited to your checking account.",
            None,
        ),
        (
            "paypal",
            "PayPal <service@paypal.com>",
            "You received a payment of $120.00 USD",
            "Jordan sent you $120.00. The money is available in your PayPal balance.",
            None,
        ),
    ]
    for slug, sender, subject, body, route in payment_recv:
        cases.append(
            case(
                id=f"gold_payment_received_{slug}",
                expected_label_key="payment-received",
                expected_route=route,
                notes=f"payment-received variant {slug}",
                message=_msg(
                    gmail_id=f"msg_pr_{slug}",
                    thread_id=f"thr_pr_{slug}",
                    sender=sender,
                    to="user@example.com",
                    subject=subject,
                    date="Mon, 11 Aug 2025 10:00:00 +0000",
                    body_plain=body,
                ),
            )
        )

    # --- bill-due ---
    bill_due = [
        (
            "electric",
            "Electric Co <billing@utility.example>",
            "Your electricity bill is due March 20",
            "Amount due $118.22. Pay by March 20.",
        ),
        (
            "cc",
            "Chase <creditcards@chase.com>",
            "Reminder: credit card payment due tomorrow",
            "Minimum payment due $35. Full balance $1,204.11.",
        ),
        (
            "invoice",
            "Acme Billing <billing@acme.example>",
            "Invoice #1042 is ready — amount due $1,200",
            "Please remit $1,200 by Apr 1. Invoice attached as PDF link.",
        ),
        (
            "water",
            "City Water <noreply@citywater.example>",
            "Water bill of $42.10 is due",
            "Your residential water bill is due in 7 days.",
        ),
        (
            "phone",
            "Verizon <verizon@email.verizonwireless.com>",
            "Your wireless bill is ready to pay",
            "Amount due $89.00 by Aug 28. Autopay is off.",
        ),
        (
            "rent",
            "Property Mgmt <billing@apartments.example>",
            "August rent invoice — amount owed $2,150",
            "Rent for unit 4B is due on the 1st.",
        ),
    ]
    for slug, sender, subject, body in bill_due:
        cases.append(
            case(
                id=f"gold_bill_due_{slug}",
                expected_label_key="bill-due",
                notes=f"bill-due variant {slug}",
                message=_msg(
                    gmail_id=f"msg_bd_{slug}",
                    thread_id=f"thr_bd_{slug}",
                    sender=sender,
                    to="user@example.com",
                    subject=subject,
                    date="Mon, 11 Aug 2025 11:00:00 +0000",
                    body_plain=body,
                ),
            )
        )

    # --- subscription-renewal ---
    subs = [
        (
            "netflix",
            "Netflix <info@mailer.netflix.com>",
            "Your membership will renew on April 1",
            "Your plan renews soon. No action needed.",
        ),
        (
            "spotify",
            "Spotify <no-reply@spotify.com>",
            "Spotify Premium auto-renewal receipt",
            "We'll renew Premium for $10.99 on Aug 20.",
        ),
        (
            "github",
            "GitHub <billing@github.com>",
            "GitHub Pro will renew for $4",
            "Your GitHub Pro subscription renews in 3 days.",
        ),
        (
            "notion",
            "Notion <noreply@notion.so>",
            "Your Notion Plus subscription renews soon",
            "Next charge $10 on Sep 1.",
        ),
        (
            "adobe",
            "Adobe <mail@adobe.com>",
            "Upcoming renewal for Creative Cloud",
            "Your annual plan renews on Sep 12 for $59.99/mo.",
        ),
        (
            "nytimes",
            "NYT <nytdirect@nytimes.com>",
            "Your New York Times subscription renews",
            "Digital All Access renews automatically next month.",
        ),
    ]
    for slug, sender, subject, body in subs:
        cases.append(
            case(
                id=f"gold_subscription_{slug}",
                expected_label_key="subscription-renewal",
                notes=f"subscription-renewal variant {slug}",
                message=_msg(
                    gmail_id=f"msg_sub_{slug}",
                    thread_id=f"thr_sub_{slug}",
                    sender=sender,
                    to="user@example.com",
                    subject=subject,
                    date="Mon, 11 Aug 2025 12:00:00 +0000",
                    body_plain=body,
                ),
            )
        )

    # --- security-alert ---
    security = [
        (
            "google",
            "Google <no-reply@accounts.google.com>",
            "Security alert: new sign-in on Mac",
            "New sign-in on a Mac device in Austin, TX.",
            "apply",
        ),
        (
            "google_pw",
            "Google <no-reply@accounts.google.com>",
            "Your password was changed",
            "The password for your Google Account was changed.",
            "apply",
        ),
        (
            "github",
            "GitHub <noreply@github.com>",
            "Suspicious login attempt blocked",
            "We blocked a suspicious sign-in to your GitHub account.",
            "apply",
        ),
        (
            "apple",
            "Apple <no_reply@email.apple.com>",
            "Your Apple ID was used to sign in to iCloud on a new device",
            "If this was you, no action is needed.",
            None,
        ),
        (
            "okta",
            "Okta <noreply@okta.com>",
            "New device enrolled for MFA",
            "A new authenticator device was added to your account.",
            None,
        ),
        (
            "slack",
            "Slack <noreply@slack.com>",
            "New login to your Slack workspace",
            "Someone signed in to Acme workspace from Chrome on Windows.",
            None,
        ),
    ]
    for slug, sender, subject, body, route in security:
        cases.append(
            case(
                id=f"gold_security_{slug}",
                expected_label_key="security-alert",
                expected_route=route,
                notes=f"security-alert variant {slug}",
                message=_msg(
                    gmail_id=f"msg_sec_{slug}",
                    thread_id=f"thr_sec_{slug}",
                    sender=sender,
                    to="user@example.com",
                    subject=subject,
                    date="Mon, 11 Aug 2025 13:00:00 +0000",
                    body_plain=body,
                ),
            )
        )

    # --- otp-verification ---
    otps = [
        (
            "github",
            "GitHub <noreply@github.com>",
            "Your GitHub verification code",
            "Your verification code is 482193.",
            "apply",
        ),
        (
            "chase",
            "Chase Alerts <no.reply.alerts@chase.com>",
            "Your one-time authorization code",
            "Authorization code: 918273. Expires in 10 minutes.",
            "apply",
        ),
        (
            "generic",
            "Auth <noreply@auth.example>",
            "Your OTP is 553201",
            "One-time passcode 553201 for login.",
            "apply",
        ),
        (
            "aws",
            "Amazon Web Services <no-reply@signin.aws>",
            "Your AWS verification code",
            "Verification code: 771902.",
            "apply",
        ),
        (
            "discord",
            "Discord <noreply@discord.com>",
            "Discord login code: 229183",
            "Enter 229183 to finish signing in. It expires in 10 minutes.",
            "apply",
        ),
        (
            "bank",
            "Bank of America <onlinebanking@ealerts.bankofamerica.com>",
            "One-time passcode for your bank login",
            "Your OTP is 440192.",
            "apply",
        ),
    ]
    for slug, sender, subject, body, route in otps:
        cases.append(
            case(
                id=f"gold_otp_{slug}",
                expected_label_key="otp-verification",
                expected_route=route,
                notes=f"otp-verification variant {slug}",
                message=_msg(
                    gmail_id=f"msg_otp_{slug}",
                    thread_id=f"thr_otp_{slug}",
                    sender=sender,
                    to="user@example.com",
                    subject=subject,
                    date="Mon, 11 Aug 2025 14:00:00 +0000",
                    body_plain=body,
                ),
            )
        )

    # --- order-confirmation ---
    orders = [
        (
            "amazon",
            "Amazon.com <auto-confirm@amazon.com>",
            "Ordered: Mechanical Keyboard",
            "Thanks for your order. We will email you when it ships.",
            "apply",
        ),
        (
            "amazon2",
            "Amazon.com <auto-confirm@amazon.com>",
            "Your Amazon.com order of HDMI Cable has been received",
            "Order confirmed. Order #112-9988776.",
            "apply",
        ),
        (
            "target",
            "Target <orders@email.target.com>",
            "Thanks for your order #T99102",
            "We received your order for 2 items totaling $54.12.",
            None,
        ),
        (
            "shopify",
            "Store <orders@shop.example>",
            "Order confirmed: Wool sweater",
            "We've received your order ORD-441. Estimated ship in 2 days.",
            None,
        ),
        (
            "bestbuy",
            "Best Buy <BestBuyInfo@emailinfo.bestbuy.com>",
            "Thanks for your Best Buy order",
            "Order #BBY-1200 confirmed for MacBook sleeve.",
            None,
        ),
        (
            "etsy",
            "Etsy <noreply@etsy.com>",
            "Your Etsy order is confirmed",
            "Order from CeramicStudio is confirmed.",
            None,
        ),
    ]
    for slug, sender, subject, body, route in orders:
        cases.append(
            case(
                id=f"gold_order_{slug}",
                expected_label_key="order-confirmation",
                expected_route=route,
                notes=f"order-confirmation variant {slug}",
                message=_msg(
                    gmail_id=f"msg_ord_{slug}",
                    thread_id=f"thr_ord_{slug}",
                    sender=sender,
                    to="user@example.com",
                    subject=subject,
                    date="Mon, 11 Aug 2025 15:00:00 +0000",
                    body_plain=body,
                ),
            )
        )

    # --- shipping-update ---
    shipping = [
        (
            "amazon_ship",
            "Amazon.com <shipment-tracking@amazon.com>",
            "Your Amazon.com order of USB-C Hub has shipped",
            "Shipped with tracking TBA123.",
            "apply",
        ),
        (
            "amazon_del",
            "Amazon.com <shipment-tracking@amazon.com>",
            "Delivered: USB-C Hub",
            "Your package was delivered today at 11:42 AM.",
            "apply",
        ),
        (
            "ups",
            "UPS <mcinfo@ups.com>",
            "UPS Update: Your package is out for delivery",
            "Tracking 1Z999AA10123456784 is out for delivery.",
            None,
        ),
        (
            "fedex",
            "FedEx <fedex@fedex.com>",
            "Delivered: your item was left at the front door",
            "FedEx delivered package 7946xxxx.",
            None,
        ),
        (
            "usps",
            "USPS <usps@email.informeddelivery.usps.com>",
            "Your package is in transit",
            "USPS tracking shows in transit to local facility.",
            None,
        ),
        (
            "delay",
            "Amazon.com <shipment-tracking@amazon.com>",
            "Delayed: tracking update for your package",
            "Delivery delayed by weather. New date tomorrow.",
            "apply",
        ),
    ]
    for slug, sender, subject, body, route in shipping:
        cases.append(
            case(
                id=f"gold_shipping_{slug}",
                expected_label_key="shipping-update",
                expected_route=route,
                notes=f"shipping-update variant {slug}",
                message=_msg(
                    gmail_id=f"msg_ship_{slug}",
                    thread_id=f"thr_ship_{slug}",
                    sender=sender,
                    to="user@example.com",
                    subject=subject,
                    date="Mon, 11 Aug 2025 16:00:00 +0000",
                    body_plain=body,
                ),
            )
        )

    # --- travel-booking ---
    travel = [
        (
            "united",
            "United Airlines <united@united.com>",
            "Your upcoming trip to SFO — confirmation",
            "Flight UA123 SFO on April 4. Confirmation ABC123.",
        ),
        (
            "marriott",
            "Marriott <noreply@marriott.com>",
            "Hotel reservation at Marriott Downtown",
            "Reservation confirmed for 2 nights starting Sep 3.",
        ),
        (
            "uber",
            "Uber <uber.receipts@uber.com>",
            "Your Uber trip with UberX on Monday",
            "You rode to SFO. Total $42.10. Receipt attached in app.",
        ),
        (
            "amtrak",
            "Amtrak <noreply@amtrak.com>",
            "Your Amtrak eTicket is ready",
            "Train 2155 NYC → BOS on Aug 22. Booking PNR991.",
        ),
        (
            "airbnb",
            "Airbnb <automated@airbnb.com>",
            "Your reservation is confirmed in Lisbon",
            "Check-in Friday after 3pm. Confirmation HMXYZ.",
        ),
        (
            "delta",
            "Delta Air Lines <DeltaAirLines@delta.com>",
            "Boarding pass ready — DL 421",
            "Your boarding pass for DL 421 ATW → ATX is ready.",
        ),
    ]
    for slug, sender, subject, body in travel:
        # Uber trip receipt is travel-ish but often payment-sent; keep as travel-booking
        # for itinerary/ride receipts unless clearly a bank debit alert.
        cases.append(
            case(
                id=f"gold_travel_{slug}",
                expected_label_key="travel-booking",
                notes=f"travel-booking variant {slug}",
                message=_msg(
                    gmail_id=f"msg_tr_{slug}",
                    thread_id=f"thr_tr_{slug}",
                    sender=sender,
                    to="user@example.com",
                    subject=subject,
                    date="Mon, 11 Aug 2025 17:00:00 +0000",
                    body_plain=body,
                ),
            )
        )

    # --- newsletter ---
    newsletters = [
        (
            "tldr",
            "TLDR AI <news@tldrnewsletter.com>",
            "This week in AI research",
            "Welcome to this week's digest...",
            True,
        ),
        (
            "atlantic",
            "The Atlantic <newsletters@theatlantic.com>",
            "Your Sunday reading list from The Atlantic",
            "Five stories worth your time this weekend.",
            True,
        ),
        (
            "substack",
            "ByteSized <newsletter@substack.com>",
            "Weekly product roundup",
            "Issue #128 of the ByteSized newsletter.",
            True,
        ),
        (
            "github_blog",
            "GitHub <newsletter@github.com>",
            "GitHub Digest: this week in open source",
            "Highlights from the GitHub Blog this week.",
            True,
        ),
        (
            "stratechery",
            "Stratechery <noreply@stratechery.com>",
            "Stratechery Weekly Roundup",
            "A weekly roundup of Stratechery articles.",
            True,
        ),
        (
            "local",
            "City Bulletin <bulletin@city.example>",
            "Neighborhood weekly digest",
            "Events and notices for your district this week.",
            True,
        ),
    ]
    for slug, sender, subject, body, unsub in newsletters:
        cases.append(
            case(
                id=f"gold_newsletter_{slug}",
                expected_label_key="newsletter",
                expected_route="apply" if unsub else None,
                notes=f"newsletter variant {slug}",
                message=_msg(
                    gmail_id=f"msg_news_{slug}",
                    thread_id=f"thr_news_{slug}",
                    sender=sender,
                    to="user@example.com",
                    subject=subject,
                    date="Sun, 10 Aug 2025 08:00:00 +0000",
                    body_plain=body,
                    list_unsubscribe=(
                        "<mailto:unsub@example.com>, <https://example.com/unsub>" if unsub else None
                    ),
                ),
            )
        )

    # --- promotion ---
    promos = [
        (
            "flash",
            "Shop <deals@merchant.example>",
            "Flash sale — 40% off ends tonight",
            "Save 40% with code SAVE40.",
        ),
        (
            "exclusive",
            "Nike <nike@email.nike.com>",
            "Exclusive offer just for you",
            "Members get an extra 20% off selected styles.",
        ),
        (
            "spring",
            "Gap <gap@email.gap.com>",
            "Introducing our new spring collection",
            "Shop new arrivals before they sell out.",
        ),
        (
            "winback",
            "Spotify <no-reply@spotify.com>",
            "Come back — 3 months for $0.99",
            "A limited-time offer to restart Premium.",
        ),
        (
            "launch",
            "Notion <noreply@notion.so>",
            "Launch offer: Notion AI add-on discounted",
            "Try Notion AI at 50% off for 3 months.",
        ),
        (
            "airline_sale",
            "United <united@united.com>",
            "Flash sale: domestic flights from $59",
            "Book by midnight for travel in September.",
        ),
    ]
    for slug, sender, subject, body in promos:
        cases.append(
            case(
                id=f"gold_promo_{slug}",
                expected_label_key="promotion",
                notes=f"promotion variant {slug}",
                message=_msg(
                    gmail_id=f"msg_promo_{slug}",
                    thread_id=f"thr_promo_{slug}",
                    sender=sender,
                    to="user@example.com",
                    subject=subject,
                    date="Mon, 11 Aug 2025 18:00:00 +0000",
                    body_plain=body,
                    list_unsubscribe="<https://example.com/unsub>",
                ),
            )
        )

    # --- job-application ---
    jobs = [
        (
            "lever",
            "Jobs <noreply@lever.co>",
            "Thanks for applying to Staff Engineer at Acme",
            "We received your application.",
        ),
        (
            "interview",
            "Acme Recruiting <recruiting@acme.example>",
            "Interview scheduled with Acme hiring team",
            "Phone screen Thursday 2pm PT.",
        ),
        (
            "status",
            "Greenhouse <no-reply@greenhouse.io>",
            "Your application status has been updated",
            "Moved to onsite interview stage.",
        ),
        (
            "linkedin",
            "LinkedIn <jobs-listings@linkedin.com>",
            "InMail: Role matching your profile — Staff SWE",
            "A recruiter reached out about a Staff Engineer role.",
        ),
        (
            "offer",
            "Acme Recruiting <recruiting@acme.example>",
            "Offer update for Staff Engineer",
            "We'd like to extend a verbal offer contingent on references.",
        ),
        (
            "reject",
            "People Ops <careers@startup.example>",
            "Update on your application to Backend Engineer",
            "We've decided to move forward with other candidates.",
        ),
    ]
    for slug, sender, subject, body in jobs:
        cases.append(
            case(
                id=f"gold_job_{slug}",
                expected_label_key="job-application",
                notes=f"job-application variant {slug}",
                message=_msg(
                    gmail_id=f"msg_job_{slug}",
                    thread_id=f"thr_job_{slug}",
                    sender=sender,
                    to="user@example.com",
                    subject=subject,
                    date="Mon, 11 Aug 2025 19:00:00 +0000",
                    body_plain=body,
                ),
            )
        )

    # --- support-ticket ---
    support = [
        (
            "saas",
            "Support <support@saas.example>",
            "Re: Ticket #4821 — login issue update",
            "We're still investigating your login issue.",
        ),
        (
            "received",
            "Helpdesk <support@vendor.example>",
            "[Ticket #45821] We've received your request",
            "An agent will reply within 24 hours.",
        ),
        (
            "resolved",
            "Support <support@saas.example>",
            "Your support case was resolved",
            "Ticket #4821 marked resolved. Reply to reopen.",
        ),
        (
            "billing",
            "Billing Support <billing@saas.example>",
            "Re: Help with billing — agent reply",
            "We refunded the duplicate charge on invoice 88.",
        ),
        (
            "zendesk",
            "Acme Support <support@acme.zendesk.com>",
            "[Acme] Request received — #99102",
            "Thanks for contacting support. Ticket #99102 created.",
        ),
        (
            "shipping_help",
            "Store Support <help@shop.example>",
            "Re: Missing package — ticket update",
            "Carrier confirmed delay; we've issued a replacement.",
        ),
    ]
    for slug, sender, subject, body in support:
        cases.append(
            case(
                id=f"gold_support_{slug}",
                expected_label_key="support-ticket",
                notes=f"support-ticket variant {slug}",
                message=_msg(
                    gmail_id=f"msg_sup_{slug}",
                    thread_id=f"thr_sup_{slug}",
                    sender=sender,
                    to="user@example.com",
                    subject=subject,
                    date="Mon, 11 Aug 2025 20:00:00 +0000",
                    body_plain=body,
                ),
            )
        )

    # --- account-statement ---
    statements = [
        (
            "march",
            "Billing <billing@acme.example>",
            "Your March account statement is ready",
            "Your March account statement is attached as invoice_march.pdf.",
            "invoice_march.pdf",
        ),
        (
            "chase_cc",
            "Chase <statements@chase.com>",
            "Monthly Chase credit card statement",
            "Your August statement is ready to view online.",
        ),
        (
            "broker",
            "Fidelity <alerts@fidelity.com>",
            "Brokerage statement available to download",
            "Your July brokerage statement is now available.",
        ),
        (
            "bank",
            "Bank of America <onlinebanking@ealerts.bankofamerica.com>",
            "Your monthly checking account statement",
            "Statement period Jul 1–Jul 31 is ready.",
        ),
        (
            "amex",
            "American Express <statement@welcome.americanexpress.com>",
            "Your Amex statement is ready",
            "View activity and balance for this statement period.",
        ),
        (
            "paypal",
            "PayPal <service@paypal.com>",
            "Your PayPal monthly statement",
            "Download your monthly account summary.",
        ),
    ]
    for item in statements:
        slug, sender, subject, body = item[0], item[1], item[2], item[3]
        attach = item[4] if len(item) > 4 else None
        cases.append(
            case(
                id=f"gold_statement_{slug}",
                expected_label_key="account-statement",
                notes=f"account-statement variant {slug}",
                message=_msg(
                    gmail_id=f"msg_stmt_{slug}",
                    thread_id=f"thr_stmt_{slug}",
                    sender=sender,
                    to="user@example.com",
                    subject=subject,
                    date="Mon, 11 Aug 2025 21:00:00 +0000",
                    body_plain=body,
                    attachment_name=attach,
                ),
            )
        )

    # --- tax-document ---
    tax = [
        (
            "1099",
            "IRS <noreply@irs.gov>",
            "Your tax transcript is available",
            "A new tax transcript is ready to download.",
        ),
        (
            "w2",
            "ADP <noreply@adp.com>",
            "W-2 wage and tax statement available",
            "Your 2024 Form W-2 is ready.",
        ),
        (
            "1099nec",
            "Upwork <noreply@upwork.com>",
            "Your 1099-NEC is ready",
            "Download Form 1099-NEC for tax year 2024.",
        ),
        (
            "broker_tax",
            "Schwab <donotreply@schwab.com>",
            "Annual tax document from your broker",
            "Form 1099 Consolidated is now available.",
        ),
        (
            "gst",
            "GST Portal <noreply@gst.example>",
            "GST filing acknowledgment for Q1",
            "Your GST return acknowledgment is attached.",
        ),
        (
            "turbotax",
            "TurboTax <noreply@turbotax.intuit.com>",
            "Your tax return documents are ready",
            "Download copies of your filed return and worksheets.",
        ),
    ]
    for slug, sender, subject, body in tax:
        cases.append(
            case(
                id=f"gold_tax_{slug}",
                expected_label_key="tax-document",
                notes=f"tax-document variant {slug}",
                message=_msg(
                    gmail_id=f"msg_tax_{slug}",
                    thread_id=f"thr_tax_{slug}",
                    sender=sender,
                    to="user@example.com",
                    subject=subject,
                    date="Mon, 11 Aug 2025 22:00:00 +0000",
                    body_plain=body,
                ),
            )
        )

    # --- refund ---
    refunds = [
        (
            "amazon",
            "Amazon.com <auto-confirm@amazon.com>",
            "Refund initiated for order 111-222",
            "A refund of $29.99 has been initiated.",
        ),
        (
            "store",
            "Store <orders@shop.example>",
            "Refund of $64.00 has been issued",
            "Your return is complete — refund processing to original card.",
        ),
        (
            "chargeback",
            "Chase Alerts <no.reply.alerts@chase.com>",
            "Charge reversed for merchant ACME",
            "A provisional credit of $88.00 posted for a disputed charge.",
        ),
        (
            "airline",
            "United <united@united.com>",
            "Refund confirmation for canceled flight",
            "Refund of $430.00 for UA123 will return in 7–10 days.",
        ),
        (
            "spotify",
            "Spotify <no-reply@spotify.com>",
            "Your refund was processed",
            "We refunded $10.99 for Premium.",
        ),
        (
            "etsy",
            "Etsy <noreply@etsy.com>",
            "Your return is complete — refund processing",
            "Seller issued a refund for order #E991.",
        ),
    ]
    for slug, sender, subject, body in refunds:
        cases.append(
            case(
                id=f"gold_refund_{slug}",
                expected_label_key="refund",
                notes=f"refund variant {slug}",
                message=_msg(
                    gmail_id=f"msg_ref_{slug}",
                    thread_id=f"thr_ref_{slug}",
                    sender=sender,
                    to="user@example.com",
                    subject=subject,
                    date="Mon, 11 Aug 2025 23:00:00 +0000",
                    body_plain=body,
                ),
            )
        )

    # --- hold / no existing fit ---
    holds = [
        (
            "insurance",
            "InsureCo <policies@insure.example>",
            "Your home insurance renewal packet",
            "Please review renewal terms for policy H-9981.",
        ),
        (
            "hoa",
            "HOA Board <board@hoa.example>",
            "Annual HOA meeting agenda and proxy form",
            "Please vote on the budget amendment.",
        ),
        (
            "school",
            "School District <noreply@school.example>",
            "Parent-teacher conference signup is open",
            "Choose a 15-minute slot next week.",
        ),
        (
            "medical",
            "Clinic <noreply@clinic.example>",
            "Lab results ready in patient portal",
            "New results are available to view securely.",
        ),
        (
            "court",
            "County Court <noreply@courts.example>",
            "Jury summons — appear on Sep 15",
            "Bring photo ID to Courthouse Room 12.",
        ),
        (
            "donation",
            "Charity <giving@nonprofit.example>",
            "Thank you for volunteering last Saturday",
            "You logged 4 hours at the food bank.",
        ),
        (
            "pet",
            "Vet Clinic <noreply@vet.example>",
            "Annual vaccine reminder for Luna",
            "Rabies vaccine is due next month.",
        ),
        (
            "gov_id",
            "DMV <noreply@dmv.example>",
            "Your REAL ID appointment confirmation",
            "Appointment Tuesday 10:20 AM. Bring documents list.",
        ),
    ]
    for slug, sender, subject, body in holds:
        cases.append(
            case(
                id=f"gold_hold_{slug}",
                expected_label_key=None,
                expected_route="hold_propose",
                notes=f"expected hold/propose — {slug}",
                message=_msg(
                    gmail_id=f"msg_hold_{slug}",
                    thread_id=f"thr_hold_{slug}",
                    sender=sender,
                    to="user@example.com",
                    subject=subject,
                    date="Tue, 12 Aug 2025 09:00:00 +0000",
                    body_plain=body,
                ),
            )
        )

    # Deduplicate by id (last write wins, but we shouldn't collide).
    by_id: dict[str, dict[str, Any]] = {}
    for row in cases:
        if row["id"] in by_id:
            raise SystemExit(f"duplicate golden id: {row['id']}")
        by_id[row["id"]] = row
    return list(by_id.values())


def main() -> int:
    cases = build_cases()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8") as fh:
        for row in cases:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    from collections import Counter

    labels = Counter(c.get("expected_label_key") or "<none>" for c in cases)
    print(f"wrote {len(cases)} cases → {OUT}")
    for key, n in sorted(labels.items(), key=lambda kv: (-kv[1], kv[0])):
        print(f"  {key}: {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
