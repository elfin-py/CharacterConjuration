export default function Footer() {
  return (
    <footer className="cc-footer p-6 text-sm cc-ink w-full">
      <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between max-w-6xl mx-auto">
        <div className="space-y-2">
          <p className="cc-title text-base font-bold">Character Conjuration</p>
          <p className="text-sm">
            A final year undergraduate synoptic project by Poppy Edwards.
          </p>
          <p className="text-sm">
            Background created in{" "}
            <a className="underline" href="https://inkarnate.com/" target="_blank" rel="noreferrer">
              Inkarnate
            </a>
            .
          </p>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-sm">
          <a className="underline" href="https://github.com/elfin-py/CharacterConjuration" target="_blank" rel="noreferrer">
            GitHub repository
          </a>
          <a className="underline" href="https://github.com/elfin-py" target="_blank" rel="noreferrer">
            GitHub profile
          </a>
          <a className="underline" href="https://dnd.wizards.com/" target="_blank" rel="noreferrer">
            Dungeons &amp; Dragons official site
          </a>
          <a className="underline" href="https://gdpr.eu/" target="_blank" rel="noreferrer">
            GDPR overview
          </a>
          <a className="underline" href="https://gdpr.eu/what-is-gdpr/" target="_blank" rel="noreferrer">
            Data protection basics
          </a>
        </div>
      </div>
    </footer>
  );
}
