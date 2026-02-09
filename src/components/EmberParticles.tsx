"use client";

import { useEffect } from "react";

export default function EmberParticles() {
  useEffect(() => {
    const container = document.createElement("div");
    container.id = "ember-container";
    container.style.position = "fixed";
    container.style.inset = "0";
    container.style.pointerEvents = "none";
    container.style.zIndex = "0";
    container.style.overflow = "hidden";
    document.body.appendChild(container);

    const createEmber = () => {
      const ember = document.createElement("div");
      ember.className = "ember";
      ember.style.left = Math.random() * 100 + "%";
      ember.style.animationDuration = Math.random() * 6 + 4 + "s";
      ember.style.opacity = (Math.random() * 0.6 + 0.2).toString();
      const size = Math.random() * 4 + 2;
      ember.style.width = size + "px";
      ember.style.height = size + "px";
      container.appendChild(ember);

      setTimeout(() => {
        ember.remove();
      }, 10000);
    };

    const interval = setInterval(createEmber, 400);

    return () => {
      clearInterval(interval);
      container.remove();
    };
  }, []);

  return null;
}
