import QtQuick 2.15
import QtTest 1.2
import "../qml/InstallerFlow.js" as Flow

TestCase {
    name: "InstallerFlow"

    function test_welcome_and_hardware_are_always_reachable() {
        compare(Flow.canOpenStep(0, false, "not-run", false, "not-run"), true)
        compare(Flow.canOpenStep(1, false, "not-run", false, "not-run"), true)
    }

    function test_inventory_must_be_attempted_before_later_steps() {
        compare(Flow.canOpenStep(2, true, "not-run", true, "diagnostic-only"), true)
        compare(Flow.canOpenStep(3, true, "not-run", true, "diagnostic-only"), false)
        compare(Flow.canOpenStep(4, true, "not-run", true, "diagnostic-only"), false)
        compare(Flow.canOpenStep(3, true, "loading", true, "diagnostic-only"), false)
        compare(Flow.canOpenStep(4, true, "loading", true, "diagnostic-only"), false)
    }

    function test_successful_inventory_allows_choices_and_valid_review() {
        compare(Flow.canOpenStep(3, true, "loaded", true, "diagnostic-only"), true)
        compare(Flow.canOpenStep(4, true, "loaded", true, "diagnostic-only"), true)
    }

    function test_empty_inventory_is_a_completed_read_only_attempt() {
        compare(Flow.canOpenStep(3, true, "loaded", true, "diagnostic-only"), true)
        compare(Flow.canOpenStep(4, true, "loaded", true, "diagnostic-only"), true)
    }

    function test_unavailable_inventory_allows_only_unselected_preview() {
        compare(Flow.canOpenStep(3, true, "unavailable", true, "diagnostic-only"), true)
        compare(Flow.canOpenStep(4, true, "unavailable", true, "diagnostic-only"), true)
        compare(Flow.canOpenStep(4, true, "unavailable", false, "invalid"), false)
    }

    function test_blocked_plan_can_be_reviewed_only_after_inventory_finishes() {
        compare(Flow.canOpenStep(4, true, "loading", false, "blocked"), false)
        compare(Flow.canOpenStep(4, true, "loaded", false, "blocked"), true)
        compare(Flow.canOpenStep(4, true, "unavailable", false, "blocked"), true)
    }

    function test_review_finish_requires_explicit_acknowledgement() {
        compare(Flow.canFinishReview(false), false)
        compare(Flow.canFinishReview(true), true)
        compare(Flow.canFinishReview(1), false)
    }
}
