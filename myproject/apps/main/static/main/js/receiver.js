/*
 * RescueBite - NGO receiver dashboard behaviour.
 * Claim a donation, then leave a review. Endpoints and payload shape are
 * unchanged; the URL arrives via a data attribute instead of inline JS.
 */
(function () {
    'use strict';

    var RB = window.RescueBite;

    document.addEventListener('DOMContentLoaded', function () {
        var list = document.getElementById('donorList');
        if (!list) {
            return;
        }

        var acceptUrl = list.dataset.rbAcceptUrl;
        var confirmModalEl = document.getElementById('confirmModal');
        var reviewModalEl = document.getElementById('reviewModal');
        var popupMessage = document.getElementById('popupMessage');
        var yesBtn = document.getElementById('yesBtn');
        var submitReview = document.getElementById('submitReview');
        var feedback = document.getElementById('feedback');
        var ratingHint = document.getElementById('ratingHint');
        var stars = Array.prototype.slice.call(
            document.querySelectorAll('.rating-stars [data-star]')
        );

        var confirmModal = new bootstrap.Modal(confirmModalEl);
        var reviewModal = new bootstrap.Modal(reviewModalEl);

        var currentFoodId = null;
        var rating = 0;

        function itemFor(id) {
            return document.querySelector('.donor-item[data-id="' + id + '"]');
        }

        function paintStars(value) {
            stars.forEach(function (star) {
                var on = Number(star.dataset.star) <= Number(value);
                star.classList.toggle('is-on', on);
                star.setAttribute('aria-pressed', on ? 'true' : 'false');
            });
            if (ratingHint) {
                ratingHint.textContent = value
                    ? 'Rated ' + value + ' out of 5'
                    : 'Tap a star to rate the handover. Optional.';
            }
        }

        function startClaim(button) {
            currentFoodId = button.dataset.rbClaim;
            var donorName = button.dataset.name || '';

            popupMessage.textContent = 'Do you want to claim the donation from';
            var strong = document.createElement('strong');
            strong.className = 'rb-confirm__donor';
            strong.textContent = donorName;
            popupMessage.appendChild(strong);

            confirmModal.show();
        }

        function showReview(id) {
            currentFoodId = id;
            reviewModal.show();
        }

        /* A claimed card switches to an "Assigned to you" badge plus the review
           action, so the list reflects the new state without a reload. */
        function markClaimed(item) {
            if (!item) {
                return;
            }
            var badge = item.querySelector('.rb-status');
            if (badge) {
                badge.className = 'rb-status rb-status--assigned';
                badge.innerHTML = '<span class="rb-status__dot" aria-hidden="true"></span>Assigned to you';
            }
            var actions = item.querySelector('.actions');
            if (actions) {
                var button = document.createElement('button');
                button.type = 'button';
                button.className = 'rb-btn rb-btn--secondary rb-btn--block';
                button.setAttribute('data-rb-review', currentFoodId);
                button.textContent = 'Leave a review';
                actions.textContent = '';
                actions.appendChild(button);
            }
        }

        list.addEventListener('click', function (event) {
            var claim = event.target.closest('[data-rb-claim]');
            if (claim) {
                startClaim(claim);
                return;
            }
            var review = event.target.closest('[data-rb-review]');
            if (review) {
                showReview(review.dataset.rbReview);
            }
        });

        yesBtn.addEventListener('click', function () {
            yesBtn.disabled = true;
            var original = yesBtn.textContent;
            yesBtn.textContent = 'Claiming…';
            fetch(acceptUrl, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': RB.getCSRF()
                },
                body: JSON.stringify({ food_id: currentFoodId })
            })
                .then(function (response) {
                    return response.json();
                })
                .then(function (data) {
                    var item = itemFor(currentFoodId);
                    if (data.success) {
                        markClaimed(item);
                        RB.toast('Success! You have claimed the donation.', 'success');
                    } else {
                        RB.toast('Error: ' + (data.error || 'Could not claim'), 'error');
                    }
                })
                .catch(function () {
                    RB.toast('Network error occurred.', 'error');
                })
                .then(function () {
                    yesBtn.disabled = false;
                    yesBtn.textContent = original;
                    confirmModal.hide();
                });
        });

        stars.forEach(function (star, index) {
            star.setAttribute('aria-pressed', 'false');
            star.addEventListener('mouseover', function () {
                paintStars(star.dataset.star);
            });
            star.addEventListener('focus', function () {
                paintStars(star.dataset.star);
            });
            star.addEventListener('click', function () {
                rating = star.dataset.star;
                paintStars(rating);
            });
            star.addEventListener('mouseleave', function () {
                paintStars(rating);
            });
            star.addEventListener('blur', function () {
                paintStars(rating);
            });
            /* Left/right arrows move between stars, matching the tab pattern. */
            star.addEventListener('keydown', function (event) {
                var next = null;
                if (event.key === 'ArrowRight' || event.key === 'ArrowDown') {
                    next = stars[(index + 1) % stars.length];
                } else if (event.key === 'ArrowLeft' || event.key === 'ArrowUp') {
                    next = stars[(index - 1 + stars.length) % stars.length];
                }
                if (next) {
                    event.preventDefault();
                    next.focus();
                }
            });
        });

        submitReview.addEventListener('click', function () {
            var item = itemFor(currentFoodId);
            if (item) {
                item.remove();
            }
            RB.toast('Thank you for your feedback!', 'success');
            reviewModal.hide();

            rating = 0;
            feedback.value = '';
            paintStars(0);
        });
    });
}());