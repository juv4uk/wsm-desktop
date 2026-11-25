.pragma library

function canOpenStep(step, reportReady, diskInventoryState, planAvailable, planStatus) {
    if (step === 0 || step === 1)
        return true
    if (!reportReady)
        return false
    if (step === 2)
        return true

    var inventorySettled = diskInventoryState === "loaded"
        || diskInventoryState === "unavailable"
    if (!inventorySettled)
        return false
    if (step === 3)
        return true
    if (step === 4)
        return planAvailable || planStatus === "blocked"
    return false
}

function canFinishReview(reviewAcknowledged) {
    return reviewAcknowledged === true
}
