class WordState:
    """Enumeration of word confidence states."""
    PROVISIONAL = "provisional"  # Low confidence, may change
    CONFIRMED = "confirmed"      # High confidence, locked in
    REVISED = "revised"          # Was provisional, now updated


class Word:
    """
    Word token used across the app.

    Transcription data (set at creation):
        text, startTime, endTime, confidence, avg_logprob, no_speech_prob,
        state, id.

    Definition data (populated lazily by controller):
        simple_result  — dict from fetch_definition() (definition, grammar).
        detail_result  — dict from fetch_details()  (senses, forms, pronunciations).
    """

    # ── confidence thresholds ─────────────────────────────────────────
    LOGPROB_THRESHOLD = -0.40
    CONFIDENCE_THRESHOLD = 0.65

    _id_counter = 0  # Class variable for unique IDs

    def __init__(
        self,
        text: str,
        startTime: float,
        endTime: float,
        confidence: float | None = None,
        avg_logprob: float | None = None,
        no_speech_prob: float | None = None,
        state: str | None = None,
    ):
        self.text = text.strip()
        self.startTime = float(startTime)
        self.endTime = float(endTime)

        self.confidence = float(confidence) if confidence is not None else None
        self.avg_logprob = float(avg_logprob) if avg_logprob is not None else None
        self.no_speech_prob = float(no_speech_prob) if no_speech_prob is not None else None

        # Assign unique ID for tracking
        Word._id_counter += 1
        self.id = Word._id_counter

        # Determine state if not provided
        if state is not None:
            self.state = state
        else:
            self.state = self._determine_initial_state()

        # Definition data (populated lazily via controller)
        self.simple_result: dict | None = None
        self.detail_result: dict | None = None

    # ── definition convenience properties ─────────────────────────────
    @property
    def is_definition_loaded(self) -> bool:
        return self.simple_result is not None

    @property
    def definition(self) -> str:
        if self.simple_result:
            return self.simple_result.get("definition", "")
        return ""

    @property
    def grammar(self) -> str:
        if self.simple_result:
            return self.simple_result.get("grammar", "")
        return ""

    @property
    def details(self) -> dict:
        if self.detail_result:
            return self.detail_result.get("details", {})
        return {}

    # ── confidence state ──────────────────────────────────────────────
    def _determine_initial_state(self) -> str:
        """Determine if word should start as confirmed or provisional."""
        if self.avg_logprob is not None and self.avg_logprob >= self.LOGPROB_THRESHOLD:
            return WordState.CONFIRMED

        if self.confidence is not None and self.confidence >= self.CONFIDENCE_THRESHOLD:
            return WordState.CONFIRMED

        return WordState.PROVISIONAL
    
    @property
    def is_provisional(self) -> bool:
        """Return True if this word is provisional (low confidence)."""
        return self.state == WordState.PROVISIONAL
    
    @property
    def is_confirmed(self) -> bool:
        """Return True if this word is confirmed (high confidence)."""
        return self.state == WordState.CONFIRMED
    
    @property
    def is_revised(self) -> bool:
        """Return True if this word was just revised."""
        return self.state == WordState.REVISED
    
    def confirm(self):
        """Mark word as confirmed."""
        if self.state == WordState.PROVISIONAL:
            self.state = WordState.CONFIRMED
    
    def mark_revised(self):
        """Mark word as revised (for visual flash effect)."""
        self.state = WordState.REVISED
    
    def __repr__(self):
        return f"Word('{self.text}', {self.startTime:.2f}-{self.endTime:.2f}, {self.state})"