/**
 * The one nod to the era (brief §5). Attribution is rendered, not just
 * stored, because these images are only freely licensed on that condition.
 */

import { MANAGER_PHOTOS } from '@/lib/managerPhotos'

export function ManagerPhotos() {
  return (
    <div className="managers">
      {MANAGER_PHOTOS.map((m) => (
        <figure className="managers__item" key={m.name}>
          <div className="managers__art">
            <img src={m.src} alt={`${m.name} at ${m.club}, ${m.year}`} loading="lazy" />
          </div>
          <figcaption>
            <p className="managers__name">{m.name}</p>
            <p className="managers__meta">
              {m.club} · {m.year}
            </p>
            <p className="managers__credit">
              <a href={m.sourceUrl} target="_blank" rel="noreferrer noopener">
                {m.photographer}
              </a>
              {' · '}
              <a href={m.licenseUrl} target="_blank" rel="noreferrer noopener">
                {m.license}
              </a>
            </p>
          </figcaption>
        </figure>
      ))}
    </div>
  )
}
