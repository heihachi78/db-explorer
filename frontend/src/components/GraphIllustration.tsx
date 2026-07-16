export function HeroGraphIllustration() {
  return (
    <svg
      className="hero-graph"
      viewBox="0 0 380 230"
      role="img"
      aria-label="Kapcsolódó adatbázis-objektumok sematikus gráfja"
    >
      <g className="hero-graph-grid" aria-hidden="true">
        <circle cx="188" cy="116" r="88" />
        <circle cx="188" cy="116" r="54" />
      </g>
      <g className="hero-graph-edges" aria-hidden="true">
        <path d="M47 119 L132 48 L161 139 L47 119" />
        <path d="M132 48 L253 83 L161 139" />
        <path d="M253 83 L331 55" />
        <path d="M253 83 L296 166 L225 190 L161 139" />
        <path className="hero-graph-edge--dashed" d="M296 166 L348 130" />
      </g>
      <g className="hero-graph-labels" aria-hidden="true">
        <text x="26" y="145">VIEW</text>
        <text x="111" y="24">TABLE</text>
        <text x="143" y="169">PACKAGE</text>
        <text x="238" y="59">TABLE</text>
        <text x="281" y="198">VIEW</text>
      </g>
      <g className="hero-graph-nodes" aria-hidden="true">
        <circle className="graph-node graph-node--navy" cx="47" cy="119" r="9" />
        <circle className="graph-node graph-node--orange graph-node--focus" cx="132" cy="48" r="11" />
        <circle className="graph-node graph-node--cyan" cx="161" cy="139" r="10" />
        <circle className="graph-node graph-node--orange" cx="253" cy="83" r="10" />
        <circle className="graph-node graph-node--purple" cx="225" cy="190" r="8" />
        <circle className="graph-node graph-node--cyan" cx="296" cy="166" r="10" />
        <circle className="graph-node graph-node--muted" cx="331" cy="55" r="7" />
        <circle className="graph-node graph-node--external" cx="348" cy="130" r="7" />
      </g>
    </svg>
  );
}

export function EmptyGraphIllustration() {
  return (
    <svg
      className="empty-graph-illustration"
      viewBox="0 0 180 112"
      role="img"
      aria-label="Kijelölésre váró gráf"
    >
      <g className="empty-graph-edges" aria-hidden="true">
        <path d="M25 72 L70 28 L104 63 L148 27" />
        <path d="M25 72 L86 91 L104 63 L151 88" />
      </g>
      <g aria-hidden="true">
        <circle className="graph-node graph-node--navy" cx="25" cy="72" r="7" />
        <circle className="graph-node graph-node--orange" cx="70" cy="28" r="8" />
        <circle className="graph-node graph-node--cyan" cx="104" cy="63" r="9" />
        <circle className="graph-node graph-node--muted" cx="148" cy="27" r="6" />
        <circle className="graph-node graph-node--purple" cx="86" cy="91" r="6" />
        <circle className="graph-node graph-node--external" cx="151" cy="88" r="6" />
      </g>
    </svg>
  );
}

export function ConnectionIllustration() {
  return (
    <svg
      className="connection-illustration"
      viewBox="0 0 140 100"
      role="img"
      aria-label="Kapcsolatra váró adatbázis"
    >
      <g className="connection-database" aria-hidden="true">
        <ellipse cx="42" cy="25" rx="27" ry="11" />
        <path d="M15 25 V67 C15 73 27 78 42 78 C57 78 69 73 69 67 V25" />
        <path d="M15 46 C15 52 27 57 42 57 C57 57 69 52 69 46" />
      </g>
      <g className="connection-link" aria-hidden="true">
        <path d="M69 51 H101" />
        <circle cx="110" cy="51" r="9" />
        <path d="M117 44 L127 34" />
        <circle cx="130" cy="31" r="4" />
      </g>
    </svg>
  );
}
