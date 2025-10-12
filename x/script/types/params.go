package types

// No script module params at this time (historical query fields removed)

// NewParams creates a new Params instance with given values
func NewParams() Params { return Params{} }

// DefaultParams returns a default set of parameters
func DefaultParams() Params { return NewParams() }

// Validate validates the params
func (p Params) Validate() error { return nil }

// No validation needed; empty params
