// The project page (/about): the landing page for judges, sponsors and anyone who arrives without a guide. Sections live in
// components/landing/. See DESIGN.md, Project page: the one place with a hero, a loop and scroll reveals, all off with reduced motion.

import { Hero, Navbar, SponsorStrip } from "@/components/landing/top";
import { ClosingCta, Footer, Journey, Proof, ScamStory, Security } from "@/components/landing/sections";

export function About() {
  return (
    <div className="min-h-screen bg-paper text-ink">
      <a href="#journey" className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-30 focus:rounded-md focus:bg-surface focus:px-3 focus:py-2">
        Skip to how it works
      </a>
      <Navbar />
      <main>
        <Hero />
        <SponsorStrip />
        <Journey />
        <ScamStory />
        <Security />
        <Proof />
        <ClosingCta />
      </main>
      <Footer />
    </div>
  );
}
