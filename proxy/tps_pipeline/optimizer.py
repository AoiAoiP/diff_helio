#!/usr/bin/env python3
"""Adam optimizer for bolt height optimization."""

import numpy as np


class AdamOptimizer:
    """Adam optimizer over bolt height vector.

    Matches C++ pipeline parameters:
      lr=2e-4, beta1=0.9, beta2=0.999, eps=1e-8
    """

    def __init__(self, n_params, lr=2e-4, beta1=0.9, beta2=0.999, eps=1e-8,
                 min_lr=1e-8, lr_decay=1.0):
        self.n = n_params
        self.init_lr = lr
        self.lr = lr
        self.beta1 = beta1
        self.beta2 = beta2
        self.eps = eps
        self.min_lr = min_lr
        self.lr_decay = lr_decay  # multiplicative decay per step (< 1.0 for decay)
        self.m = np.zeros(n_params)
        self.v = np.zeros(n_params)
        self.t = 0

    def step(self, params, grad):
        """Update parameters given gradient. Returns updated params (in-place)."""
        self.t += 1

        # Decay learning rate
        self.lr = max(self.init_lr * (self.lr_decay ** (self.t - 1)), self.min_lr)

        # Adam moments
        self.m = self.beta1 * self.m + (1.0 - self.beta1) * grad
        self.v = self.beta2 * self.v + (1.0 - self.beta2) * grad * grad

        # Bias correction
        m_hat = self.m / (1.0 - self.beta1 ** self.t)
        v_hat = self.v / (1.0 - self.beta2 ** self.t)

        # Update
        update = self.lr * m_hat / (np.sqrt(v_hat) + self.eps)
        params -= update

        return params

    def get_state(self):
        return {
            't': self.t, 'lr': self.lr,
            'm': self.m.copy(), 'v': self.v.copy(),
        }
