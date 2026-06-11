document.addEventListener('DOMContentLoaded', () => {
    const summarizeForm   = document.getElementById('summarize-form');
    const urlInput        = document.getElementById('url-input');
    const submitButton    = document.getElementById('submit-button');
    const resultContainer = document.getElementById('result-container');
    const loader          = document.getElementById('loader');
    const errorMessage    = document.getElementById('error-message');

    summarizeForm.addEventListener('submit', (e) => {
        // ❌ stop normal form submit so we can validate first
        e.preventDefault();

        clearResults();

        const url = urlInput.value.trim();

        // CONDITION 1: cannot be empty
        if (!url) {
            displayError("URL cannot be empty.");
            return;
        }

        // Basic URL validation
        if (!isValidUrl(url)) {
            displayError("Please enter a valid URL starting with http:// or https://");
            return;
        }

        // ✅ At this point URL is non-empty and valid

        // Show loading UI
        setLoading(true);

        // CONDITION 2: go to next route only on submit (and only if valid)
        const target = summarizeForm.action + '?url=' + encodeURIComponent(url);
        window.location.href = target;
    });

    // === Helpers ===

    function displayError(message) {
        resultContainer.classList.remove('hidden');  // make error area visible
        loader.classList.add('hidden');              // no spinner on error
        errorMessage.textContent = message;
        errorMessage.classList.remove('hidden');
    }

    function clearResults() {
        resultContainer.classList.add('hidden');
        errorMessage.classList.add('hidden');
        errorMessage.textContent = '';
    }

    function setLoading(isLoading) {
        if (isLoading) {
            submitButton.disabled = true;
            submitButton.textContent = 'Loading...'; // change text if you want
            resultContainer.classList.remove('hidden');
            loader.classList.remove('hidden');
        } else {
            submitButton.disabled = false;
            submitButton.textContent = 'Submit';
            loader.classList.add('hidden');
        }
    }

    // Simple URL validation
    function isValidUrl(string) {
        try {
            new URL(string);
            return true;
        } catch (_) {
            return false;
        }
    }
});
